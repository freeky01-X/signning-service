import importlib
import unittest

from sqlalchemy import String, create_engine, select
from sqlalchemy.dialects import mysql, postgresql
from sqlalchemy.schema import CreateColumn, CreateTable

from config.database import Base
from module_admin.entity.do.config_do import SysConfig
from module_admin.entity.do.menu_do import SysMenu
from plugins.core.management.entity.do.models import SysPlugin


class EntityServerDefaultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # 注册启动建表及插件使用的实体，检查各表的字符串默认值。
        for module_name in (
            'module_admin.entity.do.dept_do',
            'module_admin.entity.do.dict_do',
            'module_admin.entity.do.file_do',
            'module_admin.entity.do.job_do',
            'module_admin.entity.do.log_do',
            'module_admin.entity.do.notice_do',
            'module_admin.entity.do.post_do',
            'module_admin.entity.do.role_do',
            'module_admin.entity.do.user_do',
            'module_generator.entity.do.gen_do',
            'plugins.ai.entity.do.ai_model_do',
        ):
            importlib.import_module(module_name)

    def test_string_defaults_fit_columns_and_do_not_store_sql_quotes(self) -> None:
        for table in Base.metadata.tables.values():
            for column in table.columns:
                if not isinstance(column.type, String) or column.server_default is None:
                    continue
                value = column.server_default.arg
                if not isinstance(value, str):
                    continue
                with self.subTest(table=table.name, column=column.name):
                    self.assertNotEqual(value, "''", '空字符串默认值不能包含 SQL 引号')
                    if column.type.length is not None:
                        self.assertLessEqual(len(value), column.type.length)

    def test_mysql_and_postgresql_ddl_use_empty_string_defaults(self) -> None:
        for dialect in (mysql.dialect(), postgresql.dialect()):
            for table in Base.metadata.tables.values():
                for column in table.columns:
                    if not isinstance(column.type, String):
                        continue
                    with self.subTest(dialect=dialect.name, table=table.name, column=column.name):
                        ddl = str(CreateColumn(column).compile(dialect=dialect))
                        self.assertNotIn("DEFAULT ''''''", ddl)
            menu_ddl = str(CreateTable(SysMenu.__table__).compile(dialect=dialect))
            menu_type_line = next(line for line in menu_ddl.splitlines() if 'menu_type ' in line)
            self.assertIn("DEFAULT ''", menu_type_line)

    def test_insert_omitting_fields_stores_empty_strings(self) -> None:
        # 在独立内存数据库验证真实默认值，不连接开发数据库。
        engine = create_engine('sqlite:///:memory:')
        cases = (
            (
                SysMenu.__table__,
                {'menu_id': 1, 'menu_name': '默认值测试'},
                ('menu_type', 'path', 'route_name', 'create_by', 'update_by', 'remark'),
            ),
            (
                SysConfig.__table__,
                {'config_id': 1},
                ('config_name', 'config_key', 'config_value', 'create_by', 'update_by'),
            ),
            (
                SysPlugin.__table__,
                {'plugin_id': 'default-test', 'plugin_name': 'Test', 'version': '1.0.0'},
                ('create_by', 'update_by'),
            ),
        )
        try:
            with engine.begin() as connection:
                for table, values, fields in cases:
                    with self.subTest(table=table.name):
                        table.create(connection)
                        connection.execute(table.insert().values(**values))
                        result = connection.execute(select(*(table.c[name] for name in fields))).one()
                        self.assertEqual(tuple(result), ('',) * len(fields))
        finally:
            engine.dispose()
