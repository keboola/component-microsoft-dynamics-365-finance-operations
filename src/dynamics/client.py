import logging
import os
import xml.etree.ElementTree as ET

import requests
from keboola.component import UserException
from keboola.http_client import HttpClient
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class DynamicsClient(HttpClient):
    MSFT_LOGIN_URL = 'https://login.microsoftonline.com/common/oauth2/token'
    MAX_RETRIES = 7
    PAGE_SIZE = 2000

    def __init__(self, client_id, client_secret, resource_url, refresh_token, max_page_size: int = PAGE_SIZE):

        self.client_id = client_id
        self.client_secret = client_secret
        self.resource_url = os.path.join(resource_url, '')
        self._refresh_token = refresh_token
        self._max_page_size = max_page_size
        _accessToken = self.refresh_token()
        super().__init__(base_url=os.path.join(resource_url, 'data'), max_retries=self.MAX_RETRIES, auth_header={
            'Authorization': f'Bearer {_accessToken}'
        })

    def refresh_token(self):

        headers_refresh = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }

        body_refresh = {
            'client_id': self.client_id,
            'grant_type': 'refresh_token',
            'client_secret': self.client_secret,
            'resource': self.resource_url,
            'refresh_token': self._refresh_token
        }

        resp = requests.post(self.MSFT_LOGIN_URL, headers=headers_refresh, data=body_refresh)
        code, response_json = resp.status_code, resp.json()

        if code == 200:
            logging.debug("Access token refreshed successfully.")
            return response_json['access_token']

        else:
            raise UserException(f"Could not refresh access token. Received {code} - {response_json}.")

    def __response_hook(self, res, *args, **kwargs):

        if res.status_code == 401:
            token = self._refresh_token()
            self.update_auth_header({"Authorization": f'Bearer {token}'})

            res.request.headers['Authorization'] = f'Bearer {token}'
            s = requests.Session()
            return self.requests_retry_session(session=s).send(res.request)

    def requests_retry_session(self, session=None):

        session = session or requests.Session()
        retry = Retry(
            total=self.max_retries,
            read=self.max_retries,
            connect=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=self.status_forcelist,
            allowed_methods=('GET', 'POST', 'PATCH', 'UPDATE', 'DELETE')
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        # append response hook
        session.hooks['response'].append(self.__response_hook)
        return session

    def list_entity_metadata(self) -> dict:

        url = os.path.join(self.resource_url, 'Metadata/DataEntities')

        response = self.get_raw(url, is_absolute_path=True)
        try:
            response.raise_for_status()
            json_data = response.json()
            return json_data['value']

        except requests.HTTPError as e:
            raise e

    def download_data(self, endpoint, query=None, next_link_url=None):

        prefer_value = f"odata.maxpagesize={self._max_page_size}"

        headers_query = {
            'Prefer': prefer_value
        }

        if next_link_url:
            url_query = next_link_url

        else:
            url_query = os.path.join(self.base_url, endpoint)

            if query is not None and query != '':
                url_query += '?' + query

        response = self.get_raw(url_query, headers=headers_query, is_absolute_path=True)
        try:
            response.raise_for_status()
            json_data = response.json()
            _results = json_data['value']
            _nextLink = json_data.get('@odata.nextLink', None)
            return _results, _nextLink

        except requests.HTTPError as e:

            _err_msg = response.json().get('error', {})

            if _err_msg and 'Could not find a property named' in _err_msg:
                _add_msg = 'When querying foreign key fields, do not forget to ommit "fk" part of the field, e.g. ' + \
                           '"fk_accountid" -> "_accountid". Please, refer to the documentation for more information.'

            else:
                _add_msg = ''

            raise UserException(''.join([f"Could not query endpoint \"{endpoint}\". ",
                                         f"Received: {response.status_code} - {_err_msg.get('message')} ",
                                         _add_msg]), _err_msg) from e

    def list_columns(self, endpoint):
        """
        List endpoint available columns
        Args:
            endpoint:

        Returns:

        """

        col_metadata = self.list_columns_from_metadata()
        return col_metadata[endpoint]['columns']

    def list_columns_from_metadata(self) -> dict:
        """
        Get column names indexed by available datasets,
            e.g. {"dataset": "columns":["col1","col2"], "primary_keys":["col1"]}
        Returns: dict

        """
        entity_metadata = self.list_entity_metadata()

        entity_metadata_mapping = {e['PublicEntityName']: e for e in entity_metadata
                                   if e['PublicCollectionName']}
        response = self.get_raw('$metadata', params={'$format': 'application/atom;odata.metadata=minimal'})

        root = ET.fromstring(response.text)
        column_names = {}
        for entity_type in root.findall('.//{http://docs.oasis-open.org/odata/ns/edm}EntityType'):
            entity_name = entity_type.attrib['Name']
            if entity_name not in entity_metadata_mapping:
                continue

            dataset_name = entity_metadata_mapping[entity_name]['PublicCollectionName']
            column_names[dataset_name] = {}
            column_names[dataset_name]['columns'] = [p.attrib for p in
                                                     entity_type.findall(
                                                         '{http://docs.oasis-open.org/odata/ns/edm}Property')]

            keys = entity_type.findall('{http://docs.oasis-open.org/odata/ns/edm}Key')
            if keys:
                column_names[dataset_name]['primary_key'] = [p.attrib['Name'] for p in keys[0].findall(
                    '{http://docs.oasis-open.org/odata/ns/edm}PropertyRef')]
            else:
                column_names[dataset_name]['primary_key'] = []

        return column_names
