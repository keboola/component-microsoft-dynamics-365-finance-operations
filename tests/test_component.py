import unittest
import mock
import os
import csv
import tempfile
from freezegun import freeze_time

import requests
from keboola.component import UserException

from component import Component
from src.dynamics.client import DynamicsClient
from src.dynamics.result import DynamicsWriter, FORMATTED_VALUE_LABEL


class TestComponent(unittest.TestCase):
    # set global time to 2010-10-10 - affects functions like datetime.now()
    @freeze_time("2010-10-10")
    # set KBC_DATADIR env to non-existing dir
    @mock.patch.dict(os.environ, {"KBC_DATADIR": "./non-existing-dir"})
    def test_run_no_cfg_fails(self):
        with self.assertRaises(ValueError):
            comp = Component()
            comp.run()


class TestODataParsing(unittest.TestCase):
    """Test OData response parsing logic."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock the token refresh to avoid actual API calls
        with mock.patch.object(DynamicsClient, "refresh_tokens", return_value="mock_access_token"):
            self.client = DynamicsClient(
                client_id="test_client_id",
                client_secret="test_client_secret",
                resource_url="https://test.dynamics.com",
                refresh_token="test_refresh_token",
            )

    @mock.patch("src.dynamics.client.HttpClient.get_raw")
    def test_parse_simple_odata_response(self, mock_get_raw):
        """Test parsing a simple OData response with results and no pagination."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [{"id": "1", "name": "Item 1"}, {"id": "2", "name": "Item 2"}, {"id": "3", "name": "Item 3"}]
        }
        mock_get_raw.return_value = mock_response

        results, next_link = self.client.download_data(endpoint="TestEntities", columns=["id", "name"])

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["id"], "1")
        self.assertEqual(results[0]["name"], "Item 1")
        self.assertIsNone(next_link)

    @mock.patch("src.dynamics.client.HttpClient.get_raw")
    def test_parse_odata_response_with_pagination(self, mock_get_raw):
        """Test parsing OData response with @odata.nextLink for pagination."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [{"id": "1", "name": "Item 1"}],
            "@odata.nextLink": "https://test.dynamics.com/data/TestEntities?$skip=1000",
        }
        mock_get_raw.return_value = mock_response

        results, next_link = self.client.download_data(endpoint="TestEntities", columns=["id", "name"])

        self.assertEqual(len(results), 1)
        self.assertEqual(next_link, "https://test.dynamics.com/data/TestEntities?$skip=1000")

    @mock.patch("src.dynamics.client.HttpClient.get_raw")
    def test_parse_odata_response_with_formatted_values(self, mock_get_raw):
        """Test parsing OData response with @OData.Community.Display.V1.FormattedValue fields."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {
                    "id": "1",
                    "statuscode": 1,
                    "statuscode@OData.Community.Display.V1.FormattedValue": "Active",
                    "modifiedon": "2024-01-15T10:30:00Z",
                    "modifiedon@OData.Community.Display.V1.FormattedValue": "1/15/2024 10:30 AM",
                }
            ]
        }
        mock_get_raw.return_value = mock_response

        results, next_link = self.client.download_data(
            endpoint="TestEntities", columns=["id", "statuscode", "modifiedon"]
        )

        # Verify all fields are present including formatted values
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "1")
        self.assertEqual(results[0]["statuscode"], 1)
        self.assertIn("statuscode@OData.Community.Display.V1.FormattedValue", results[0])
        self.assertEqual(results[0]["statuscode@OData.Community.Display.V1.FormattedValue"], "Active")

    @mock.patch("src.dynamics.client.HttpClient.get_raw")
    def test_parse_odata_response_with_foreign_keys(self, mock_get_raw):
        """Test parsing OData response with foreign key fields (starting with underscore)."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {
                    "id": "1",
                    "name": "Contact 1",
                    "_accountid_value": "acc-123",
                    "_ownerid_value": "user-456",
                    "@odata.etag": 'W/"12345"',
                }
            ]
        }
        mock_get_raw.return_value = mock_response

        results, next_link = self.client.download_data(
            endpoint="Contacts", columns=["id", "name", "_accountid_value", "_ownerid_value"]
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["_accountid_value"], "acc-123")
        self.assertEqual(results[0]["_ownerid_value"], "user-456")
        # @odata.etag should be present in raw response
        self.assertIn("@odata.etag", results[0])

    @mock.patch("src.dynamics.client.HttpClient.get_raw")
    def test_parse_empty_odata_response(self, mock_get_raw):
        """Test parsing empty OData response."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": []}
        mock_get_raw.return_value = mock_response

        results, next_link = self.client.download_data(endpoint="TestEntities", columns=["id", "name"])

        self.assertEqual(len(results), 0)
        self.assertEqual(results, [])
        self.assertIsNone(next_link)

    @mock.patch("src.dynamics.client.HttpClient.get_raw")
    def test_odata_http_error_handling(self, mock_get_raw):
        """Test handling of HTTP errors in OData responses."""
        mock_response = mock.Mock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = requests.HTTPError()
        mock_response.json.return_value = {"error": {"code": "BadRequest", "message": "Invalid query parameter"}}
        mock_get_raw.return_value = mock_response

        with self.assertRaises(UserException) as context:
            self.client.download_data(endpoint="TestEntities", columns=["invalid_column"])

        self.assertIn("Could not query endpoint", str(context.exception))
        self.assertIn("Invalid query parameter", str(context.exception))

    @mock.patch("src.dynamics.client.HttpClient.get_raw")
    def test_parse_odata_response_with_incremental_filter(self, mock_get_raw):
        """Test that incremental filters are correctly applied in the request."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": [{"id": "5", "modifiedon": "2024-12-01T00:00:00Z"}]}
        mock_get_raw.return_value = mock_response

        results, next_link = self.client.download_data(
            endpoint="TestEntities",
            columns=["id", "modifiedon"],
            incremental_field="modifiedon",
            incremental_value="2024-11-01T00:00:00Z",
        )

        # Verify the call was made with the correct filter (unencoded in the URL)
        call_args = mock_get_raw.call_args
        called_url = call_args[0][0]
        self.assertIn("$filter=modifiedon gt 2024-11-01T00:00:00Z", called_url)
        self.assertEqual(len(results), 1)


class TestDynamicsWriter(unittest.TestCase):
    """Test OData response column mapping and CSV writing."""

    def setUp(self):
        """Create a temporary file for each test."""
        self.temp_file = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv")
        self.temp_file_path = self.temp_file.name
        self.temp_file.close()
        self.writer = DynamicsWriter(self.temp_file_path)

    def tearDown(self):
        """Clean up temporary file."""
        self.writer.close()
        if os.path.exists(self.temp_file_path):
            os.remove(self.temp_file_path)

    def test_column_map_simple_columns(self):
        """Test column mapping with simple column names."""
        object_data = [
            {"id": "1", "name": "Item 1", "status": "Active"},
            {"id": "2", "name": "Item 2", "status": "Inactive"},
        ]

        self.writer.set_column_map(object_data)
        columns = self.writer.get_result_columns()

        # Simple columns should be kept as-is
        self.assertIn("id", columns)
        self.assertIn("name", columns)
        self.assertIn("status", columns)
        self.assertEqual(len(columns), 3)

    def test_column_map_formatted_value_columns(self):
        """Test column mapping with @OData.Community.Display.V1.FormattedValue columns."""
        object_data = [
            {
                "statuscode": 1,
                f"statuscode{FORMATTED_VALUE_LABEL}": "Active",
                "modifiedon": "2024-01-15T10:30:00Z",
                f"modifiedon{FORMATTED_VALUE_LABEL}": "1/15/2024 10:30 AM",
            }
        ]

        self.writer.set_column_map(object_data)
        columns = self.writer.get_result_columns()

        # Regular columns
        self.assertIn("statuscode", columns)
        self.assertIn("modifiedon", columns)

        # Formatted value columns should be shortened
        self.assertIn("statuscode_formattedValue", columns)
        self.assertIn("modifiedon_formattedValue", columns)

        # Original formatted value labels should not be in result
        self.assertNotIn(f"statuscode{FORMATTED_VALUE_LABEL}", columns)

    def test_column_map_foreign_key_columns(self):
        """Test column mapping with foreign key columns (starting with underscore)."""
        object_data = [{"id": "1", "name": "Contact 1", "_accountid_value": "acc-123", "_ownerid_value": "user-456"}]

        self.writer.set_column_map(object_data)
        columns = self.writer.get_result_columns()

        # Foreign key columns should be prefixed with 'fk'
        self.assertIn("fk_accountid_value", columns)
        self.assertIn("fk_ownerid_value", columns)

        # Regular columns unchanged
        self.assertIn("id", columns)
        self.assertIn("name", columns)

    def test_column_map_foreign_key_with_formatted_value(self):
        """Test column mapping with foreign key that has a formatted value."""
        object_data = [
            {"id": "1", "_accountid_value": "acc-123", f"_accountid_value{FORMATTED_VALUE_LABEL}": "Contoso Ltd."}
        ]

        self.writer.set_column_map(object_data)
        columns = self.writer.get_result_columns()

        # Foreign key should have 'fk' prefix
        self.assertIn("fk_accountid_value", columns)

        # Formatted value of foreign key should have both 'fk' prefix and '_formattedValue' suffix
        self.assertIn("fk_accountid_value_formattedValue", columns)

    def test_column_map_filters_odata_metadata(self):
        """Test that @odata metadata columns are filtered out."""
        object_data = [
            {
                "id": "1",
                "name": "Item 1",
                "@odata.etag": 'W/"12345"',
                "@odata.type": "#Microsoft.Dynamics.CRM.contact",
                "@odata.id": "https://test.dynamics.com/api/contacts(1)",
            }
        ]

        self.writer.set_column_map(object_data)
        columns = self.writer.get_result_columns()

        # Regular columns present
        self.assertIn("id", columns)
        self.assertIn("name", columns)

        # @odata columns should be filtered out
        self.assertNotIn("@odata.etag", columns)
        self.assertNotIn("@odata.type", columns)
        self.assertNotIn("@odata.id", columns)

    def test_column_map_mixed_columns(self):
        """Test column mapping with a mix of all column types."""
        object_data = [
            {
                "id": "1",
                "name": "Contact 1",
                "statuscode": 1,
                f"statuscode{FORMATTED_VALUE_LABEL}": "Active",
                "_accountid_value": "acc-123",
                f"_accountid_value{FORMATTED_VALUE_LABEL}": "Contoso Ltd.",
                "@odata.etag": 'W/"12345"',
            }
        ]

        self.writer.set_column_map(object_data)
        columns = self.writer.get_result_columns()

        # Regular columns
        self.assertIn("id", columns)
        self.assertIn("name", columns)
        self.assertIn("statuscode", columns)

        # Formatted value
        self.assertIn("statuscode_formattedValue", columns)

        # Foreign key
        self.assertIn("fk_accountid_value", columns)
        self.assertIn("fk_accountid_value_formattedValue", columns)

        # @odata filtered out
        self.assertNotIn("@odata.etag", columns)

    def test_writerows_creates_csv(self):
        """Test that writerows creates a proper CSV file."""
        data_to_write = [{"id": "1", "name": "Item 1"}, {"id": "2", "name": "Item 2"}]

        self.writer.writerows(data_to_write)
        self.writer.close()

        # Read back the CSV (without headers, so use csv.reader)
        with open(self.temp_file_path, "r") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Verify we have 2 rows of data
        self.assertEqual(len(rows), 2)
        # Rows are in order: id, name
        self.assertEqual(rows[0][0], "1")
        self.assertEqual(rows[0][1], "Item 1")
        self.assertEqual(rows[1][0], "2")
        self.assertEqual(rows[1][1], "Item 2")

    def test_writerows_with_formatted_values(self):
        """Test writing rows with formatted value columns."""
        data_to_write = [{"statuscode": "1", f"statuscode{FORMATTED_VALUE_LABEL}": "Active", "@odata.etag": 'W/"123"'}]

        self.writer.writerows(data_to_write)

        # Get the columns that were mapped
        columns = self.writer.get_result_columns()

        self.writer.close()

        # Verify columns mapping
        self.assertIn("statuscode", columns)
        self.assertIn("statuscode_formattedValue", columns)
        # @odata should be filtered
        self.assertNotIn("@odata.etag", columns)

        # Verify CSV was written
        with open(self.temp_file_path, "r") as f:
            content = f.read()
            self.assertIn("1", content)
            self.assertIn("Active", content)

    def test_is_formatted_value_column(self):
        """Test the helper method to identify formatted value columns."""
        self.assertTrue(self.writer._is_formatted_value_column(f"statuscode{FORMATTED_VALUE_LABEL}"))
        self.assertFalse(self.writer._is_formatted_value_column("statuscode"))
        self.assertFalse(self.writer._is_formatted_value_column("name"))


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
