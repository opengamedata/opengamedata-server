# import libraries
from flask import Flask
from flask_restful import Resource, Api, reqparse
from mysql.connector import Error as MySQLError
from mysql.connector.connection import MySQLConnection
from typing import Any, Dict, List, Tuple, Union
# import locals
from config.config import settings
from opengamedata.interfaces.MySQLInterface import SQL

class PlayerIDAPI:
    @staticmethod
    def register(app:Flask):
        # Expected WSGIScriptAlias URL path is /playerGameState
        api = Api(app)
        api.add_resource(PlayerIDAPI.GeneratePlayerID, '/players/generateId')
        api.add_resource(PlayerIDAPI.SavePlayerID, '/players/saveId')

    class GeneratePlayerID(Resource):
        @staticmethod
        def _generateID(db_conn:Union[MySQLConnection, None], db_name:str) -> Union[str,None]:
            """[summary]

            :param db_conn: [description]
            :type db_conn: Union[MySQLConnection, None]
            :param db_name: [description]
            :type db_name: str
            :raises: mysql.connector.Error
            :return: [description]
            :rtype: Union[str,None]
            """
            ret_val : Union[str,None] = None
            if db_conn is not None:
                adjective_query = f"""SELECT `word` from {db_name}.adjectives ORDER BY rand() limit 1;"""
                noun_query      = f"""SELECT `word` from {db_name}.nouns ORDER BY rand() limit 1;"""
                adjective = SQL.Query(cursor=db_conn.cursor(), query=adjective_query, params=None, fetch_results=True)
                noun = SQL.Query(cursor=db_conn.cursor(), query=noun_query, params=None, fetch_results=True)
                if adjective is not None and noun is not None and adjective != [] and noun != []:
                    ret_val = f"{adjective[0][0].capitalize()}{noun[0][0].capitalize()}"
            return ret_val

        @staticmethod
        def _unusedID(db_conn:Union[MySQLConnection, None], db_name:str, player_id:Union[str,None]) -> bool:
            """[summary]

            :param db_conn: [description]
            :type db_conn: Union[MySQLConnection, None]
            :param db_name: [description]
            :type db_name: str
            :param player_id: [description]
            :type player_id: Union[str,None]
            :raises: mysql.connector.Error
            :return: [description]
            :rtype: bool
            """
            ret_val : bool = False
            if db_conn is not None and player_id is not None:
                query = f"""SELECT COUNT(*) FROM {db_name}.player_codes WHERE `player_id`=%s;"""
                params = (player_id,)
                try:
                    count = SQL.Query(cursor=db_conn.cursor(), query=query, params=params, fetch_results=True)
                except MySQLError as err:
                    print(f"ERROR: Could not complete query to check if ID is unused, got error {err}")
                else:
                    # print(f"GOT COUNT: {count}")
                    if count is not None and count[0][0] == 0:
                        ret_val = True
            return ret_val

        def get(self):
            """API function to retrieve a randomly-generated player ID from our database.
            To generate IDs, we use one adjective and one noun.
            Our adjective list is based on:
            And the noun list comes from "The Great Noun List" at http://www.desiquintans.com/nounlist,
            by way of the Kaggle dataset at https://www.kaggle.com/leite0407/list-of-nouns/version/1

            :return: [description]
            :rtype: [type]
            """
            # Step 1: get id from SQL
            ret_val : Dict[str,Any] = {
                "type":"GET",
                "val":None,
                "msg":"",
                "status":"SUCCESS",
            }

            id_config = settings["DB_CONFIG"]["id_gen"]
            _dummy, id_conn = SQL.ConnectDB(db_settings=id_config)
            fd_config = settings["DB_CONFIG"]["fd_users"]
            _dummy, user_conn = SQL.ConnectDB(db_settings=fd_config)
            if id_conn is not None:
                try:
                    id = None
                    count = 0
                    while (not PlayerIDAPI.PlayerID._unusedID(db_conn=user_conn, db_name=fd_config["DB_NAME"], player_id=id)) and (count < 1000):
                            id = PlayerIDAPI.PlayerID._generateID(db_conn=id_conn, db_name=id_config["DB_NAME"])
                            count += 1
                except MySQLError as err:
                    ret_val['msg'] = f"ERROR: Could not complete query to check if ID is unused, a database error occurred."
                    ret_val['status'] = "ERR_DB"
                else:
            # Step 2: process and return ID.
                    if id is not None and count < 1000:
                        ret_val['val'] = id,
                        ret_val['msg'] = "SUCCESS: Loaded player from database."
                    else:
                        ret_val['msg'] = "FAIL: Could not generate new player."
                        ret_val['status'] = "ERR_SRV"
                finally:
                    SQL.disconnectMySQL(id_conn)
            else:
                ret_val['msg'] = "FAIL: Could not load player, database unavailable!"
                ret_val['status'] = "ERR_DB"
            return ret_val

    class SavePlayerID(Resource):
        def post(self):
            ret_val : Dict[str,Any] = {
                "type":"POST",
                "val":None,
                "msg":"",
                "status":"SUCCESS",
            }
            # Step 1: get args
            parser = reqparse.RequestParser()
            parser.add_argument("player_id", type=str)
            parser.add_argument("name", type=str)
            args = parser.parse_args()
            player_id = args['player_id']
            name      = args['name']

            # Step 2: insert player into the database
            fd_config = settings["DB_CONFIG"]["fd_users"]
            _dummy, db_conn = SQL.ConnectDB(db_settings=fd_config)
            if db_conn is not None:
                insert_query = f"""INSERT INTO {fd_config['DB_NAME']}.player_codes (`player_id`, `name`) VALUES (%s, %s)
                                 ON DUPLICATE KEY UPDATE `name`=%s;"""
                insert_params = (player_id, name, name)
                try:
                    SQL.Query(cursor=db_conn.cursor(), query=insert_query, params=insert_params, fetch_results=False)
                    db_conn.commit()
            # Step 3: Report status
                except MySQLError as err:
                    ret_val['msg'] = f"FAIL: Could not save new player to database, an error occurred."
                    ret_val['status'] = "ERR_DB"
                    raise err
                else:
                    ret_val['msg'] = f"SUCCESS: Saved new player to the database."
                finally:
                    SQL.disconnectMySQL(db_conn)
            else:
                ret_val['msg'] = "FAIL: Could not save new player, database unavailable!"
                ret_val['status'] = "ERR_DB"
            return ret_val