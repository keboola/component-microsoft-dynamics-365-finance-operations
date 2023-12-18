import csv

FORMATTED_VALUE_LABEL = "@OData.Community.Display.V1.FormattedValue"


class DynamicsWriter:

    def __init__(self, output_path: str):

        self.full_table_path = output_path
        self.__column_map = None
        self.__writer: csv.DictWriter = None
        self.__out_stream = None

    def set_column_map(self, object_data: dict):
        if not self.__column_map:

            all_columns = []

            for o in object_data:
                all_columns += o.keys()

            all_columns = list(all_columns)
            map_columns = {}

            for column in all_columns:
                if column.startswith('_') is True:
                    map_columns[column] = self._get_valid_kbc_storage_name(column)
                elif self._is_formatted_value_column(column):
                    map_columns[column] = self._get_shortened_formatted_value_column_name(column)
                elif '@odata' in column:
                    continue
                else:
                    map_columns[column] = column

            self.__column_map = map_columns

    def _get_valid_kbc_storage_name(self, column_name):
        if not self._is_formatted_value_column(column_name):
            return f'fk{column_name}'
        column_cleaned = self._get_shortened_formatted_value_column_name(column_name)
        return f"fk{column_cleaned}"

    @staticmethod
    def _is_formatted_value_column(column_name: str) -> bool:
        if FORMATTED_VALUE_LABEL in column_name:
            return True

    @staticmethod
    def _get_shortened_formatted_value_column_name(column_name: str) -> str:
        name_with_removed_formatted_value = column_name.replace(FORMATTED_VALUE_LABEL, "")
        return f"{name_with_removed_formatted_value}_formattedValue"

    def _get_writer(self, columns: list[str]) -> csv.DictWriter:
        if not self.__writer:
            self.__out_stream = open(self.full_table_path, 'w+')
            self.__writer = csv.DictWriter(self.__out_stream,
                                           fieldnames=columns, extrasaction='ignore')
        return self.__writer

    def get_result_columns(self) -> list[str]:
        return list(self.__column_map.values())

    def writerows(self, data_to_write: dict):
        self.set_column_map(data_to_write)
        self._get_writer(list(self.__column_map.keys())).writerows(data_to_write)

    def close(self):
        if self.__out_stream:
            self.__out_stream.close()
