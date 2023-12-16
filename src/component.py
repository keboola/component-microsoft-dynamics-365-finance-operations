import json
import logging

from keboola.component import ComponentBase, UserException
from keboola.component.base import sync_action
from keboola.component.dao import OauthCredentials
from keboola.component.sync_actions import SelectElement

from configuration import Configuration
from dynamics.client import DynamicsClient
from dynamics.result import DynamicsWriter


class Component(ComponentBase):

    def __init__(self):

        super().__init__()

        self.cfg: Configuration
        self._client: DynamicsClient = None

    def run(self):

        self.__init_configuration()
        self.init_client()

        logging.info(f"Downloading data for endpoint \"{self.cfg.endpoint}\".")

        _has_more = True
        _next_link = None
        _req_count = 0
        column_metadata = self._client.list_columns_from_metadata()
        _pk = column_metadata[self.cfg.endpoint]['primary_key']
        if not self.cfg.destination.table_name:
            res_name = f'{self.cfg.endpoint}.csv'
        else:
            res_name = f'{self.cfg.destination.table_name}.csv'

        res_table = self.create_out_table_definition(res_name,
                                                     primary_key=_pk,
                                                     incremental=self.cfg.destination.incremental)

        writer = DynamicsWriter(res_table.full_path)

        total_rows = 0
        while _has_more is True:

            _req_count += 1
            _results, _next_link = self._client.download_data(self.cfg.endpoint,
                                                              next_link_url=_next_link)  # noqa

            if len(_results) == 0:
                _has_more = False
            else:
                total_rows += len(_results)
                writer.writerows(_results)
                _has_more = True if _next_link else False

            logging.info(f"Downloaded {total_rows} rows so far.")

        logging.info(f"Made {_req_count} requests to the API in total for endpoint \"{self.cfg.endpoint}\". "
                     f"Downloaded total {total_rows} rows")

        if total_rows > 0:
            writer.close()
            res_table.columns = writer.get_result_columns()
            self.write_manifest(res_table)

    def init_client(self):
        organization_url = self.configuration.parameters.get('organization_url')
        if not organization_url:
            raise UserException('You must fill in the Organization URL')

        if custom_creds := self.configuration.parameters.get('custom_credentials'):
            credentials = OauthCredentials('', '', json.loads(custom_creds['#data']), '',
                                           custom_creds['appKey'],
                                           custom_creds['#appSecret'])
        else:
            credentials = self.configuration.oauth_credentials

        if not credentials:
            raise UserException("The configuration is not authorized. Please authorize it first.")

        refresh_token = credentials.data['refresh_token']
        self._client = DynamicsClient(credentials.appKey,
                                      credentials.appSecret, organization_url,
                                      refresh_token)

    def __init_configuration(self):
        try:
            self._validate_parameters(self.configuration.parameters, Configuration.get_dataclass_required_parameters(),
                                      'Row')
        except UserException as e:
            raise UserException(f"{e} The configuration is invalid. Please check that you added a configuration row.")
        self.cfg: Configuration = Configuration.fromDict(parameters=self.configuration.parameters)

    @sync_action('list_endpoints')
    def list_endpoints(self):
        self.init_client()
        endpoints = self._client.list_entity_metadata()
        return [SelectElement(el['PublicCollectionName']) for el in endpoints if el['PublicCollectionName']]

    @sync_action('list_columns')
    def list_columns(self):
        self.init_client()
        self.__init_configuration()
        columns = self._client.list_columns(self.cfg.endpoint)
        return [SelectElement(el) for el in columns]

    @sync_action('testConnection')
    def test_connection(self):
        self.init_client()
        self._client.list_entity_metadata()


"""
        Main entrypoint
"""
if __name__ == "__main__":
    try:
        comp = Component()
        # this triggers the run method by default and is controlled by the configuration.action parameter
        comp.execute_action()
    except UserException as exc:
        detail = ''
        if len(exc.args) > 1:
            # remove extra argument to make logging.exception log properly
            detail = exc.args[1]
            exc.args = exc.args[:1]
        logging.exception(exc, extra={"additional_detail": detail})
        exit(1)
    except Exception as exc:
        logging.exception(exc)
        exit(2)
