# import libraries
import json
from flask import Flask, request
from flask_restful import Resource, Api, reqparse
from mysql.connector import Error as MySQLError
from mysql.connector.connection import MySQLConnection
# import locals
from config.config import settings
from opengamedata.interfaces.MySQLInterface import SQL

import time

class GameStateAPI:

    @staticmethod
    def register(app:Flask):
        # Expected WSGIScriptAlias URL path is /playerGameState
        api = Api(app)
        api.add_resource(GameStateAPI.GameStateLoad, '/load')
        api.add_resource(GameStateAPI.GameStateSave, '/save')

    class GameStateLoad(Resource):
        def get(self):
            """GET request for a player's game state.
            Located at <server_addr>/playerGameState/load
            Requires 'player_id' and 'game_id'  as query string parameters.
            Optionally takes 'count' and 'offset' as query string parameters.
            Count controls the number of states to retrieve.
            Offset allows the retrieved states to be offset from the latest state.
                For example, count=1, offset=0 will retrieve the most recent state
                count=1, offset=1 will retrieve the second-most recent state

            :param player_id: A player id string.
            :type player_id: str
            :param game_id: A game id string.
            :type game_id: str
            :param count: Integer representing the total number of states to retrieve
            :type count: int
            :param offset: Integer representing offset (going backwards from the most-recent) to start retrieving. So, zero would start with the most-recent state
            :type offset: int
            :raises err: If a mysqlerror occurs, it will be raised up a level after setting an error message in the API call return value.
            :return: A dictionary containing a 'message' describing the result, and a 'state' containing either the actual state variable if found, else None
            :rtype: Dict[str, str | None]
            """
            ret_val = {
                "type":"GET",
                "val":None,
                "msg":"",
                "status":"SUCCESS",
            }

            # Step 1: get args
            parser = reqparse.RequestParser()
            parser.add_argument("player_id", type=str, required=True, location="args")
            parser.add_argument("game_id", type=str, required=True, location="args")
            parser.add_argument("count", type=int, help="Invalid count of states to retrieve, default to 1.", location="args")
            parser.add_argument("offset", type=int, help="Invalid offset of states to retrieve, default to 0.", location="args") # Query string
            args = parser.parse_args()

            player_id = args["player_id"]
            game_id = args["game_id"]
            count = args['count'] if args['count'] is not None else 1
            offset = args['offset'] if args['offset'] is not None else 0

            # Step 2: get states from database.
            fd_config = settings["DB_CONFIG"]["fd_users"]
            tunnel, db_conn = SQL.ConnectDB(db_settings=fd_config)
            if db_conn is not None:
                query_string = f"SELECT `game_state` from {fd_config['DB_NAME']}.game_states\n\
                                 WHERE `player_id`=%s AND `game_id`=%s ORDER BY `save_time` DESC LIMIT %s, %s;"
                query_params = (player_id, game_id.upper(), offset, count)
                try:
                    states = SQL.Query(cursor=db_conn.cursor(), query=query_string, params=query_params, fetch_results=True)
            # Step 3: process and return states
                except MySQLError as err:
                    ret_val['msg'] = "FAIL: Could not retrieve state(s), an error occurred!"
                    ret_val['status'] = "ERR_DB"
                    raise err
                else:
                    if states is not None:
                        if len(states) == count:
                            ret_val['val'] = [str(state[0]) for state in states]
                            ret_val['msg'] = f"SUCCESS: Retrieved {len(ret_val['val'])} states."
                        elif len(states) < count:
                            ret_val['msg'] = f"FAIL: No {game_id} states were found for player {player_id}"
                            ret_val['status'] = "ERR_REQ"
                        else: # len(states) > count
                            ret_val['msg'] = f"FAIL: Error in retrieving states, too many states returned!"
                            ret_val['status'] = "ERR_SRV"
                    else:
                        ret_val['msg'] = f"FAIL: No {game_id} states could be retrieved"
                        ret_val['status'] = "ERR_DB"
                finally:
                    SQL.disconnectMySQL(db=db_conn)
            else:
                ret_val['status'] = "ERR_DB"
                ret_val['msg'] = "FAIL: Could not retrieve state(s), database unavailable!"
            return ret_val
    
    class GameStateSave(Resource):
        def post(self):
            """POST request to store a player's game state.
            Located at <server_addr>/playerGameState/save
            
            Required data fields are expected in the request body as JSON

            The state should be a string, encoding state in whatever way is convenient to the client program.
            No formatting of the string is enforced from the database side of things.

            :param player_id: A player id string.
            :type player_id: str
            :param game_id: A game id string.
            :type game_id: str
            :param state: The player's state
            :type state: str
            :raises err: If a mysqlerror occurs, it will be raised up a level after setting an error message in the API call return value.
            :return: A dictionary containing a 'message' describing the result, and a 'state' containing either the actual state variable if found, else None
            :rtype: Dict[str, str | None]
            """            
            ret_val = {
                "type":"POST",
                "val":None,
                "msg":"",
                "status":"SUCCESS",
            }

            # Step 1: get args
            parser = reqparse.RequestParser()
            parser.add_argument("player_id", type=str, required=True)
            parser.add_argument("game_id", type=str, required=True)
            parser.add_argument("state", type=str)
            args = parser.parse_args()
            player_id = args["player_id"]
            game_id = args["game_id"]
            state = args['state']

            # Step 2: insert state into database.
            fd_config = settings["DB_CONFIG"]["fd_users"]
            _dummy, db_conn = SQL.ConnectDB(db_settings=fd_config)
            if db_conn is not None:
                query_string = f"""INSERT INTO {fd_config['DB_NAME']}.game_states (`player_id`, `game_id`, `game_state`)
                                 VALUES (%s, %s, %s);"""
                query_params = (player_id, game_id, state)
                try:
                    SQL.Query(cursor=db_conn.cursor(), query=query_string, params=query_params, fetch_results=False)
                    db_conn.commit()
            # Step 3: Report status
                except MySQLError as err:
                    ret_val['msg'] = "FAIL: Could not save state to the database, an error occurred!"
                    ret_val['status'] = "ERR_DB"
                    raise err
                else:
                    ret_val['msg'] = "SUCCESS: Saved state to the database."
                finally:
                    SQL.disconnectMySQL(db_conn)
            else:
                ret_val['msg'] = "Could not save state, database unavailable!"
                ret_val['status'] = "ERR_DB"
            return ret_val