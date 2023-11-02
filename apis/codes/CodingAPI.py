# import standard libraries
import os
import traceback
from typing import Any, Dict, Optional
# import 3rd-party libraries
from flask import Flask, current_app
from flask_restful import Resource, Api, reqparse
from mysql.connector import Error as MySQLError
from mysql.connector.connection import MySQLConnection
# import locals
from apis.APIResult import APIResult, RESTType, ResultStatus
from apis import APIUtils
from config.config import settings
from opengamedata.coding.Code import Code
from opengamedata.coding.Coder import Coder
from opengamedata.interfaces.CodingInterface import CodingInterface

class CodingAPI:
    """API for logging and retrieving game states.
    Located at <server_addr>/codes/
    Valid requests are GET and POST.
    """
    @staticmethod
    def register(app:Flask):
        # Expected WSGIScriptAlias URL path is /codes
        api = Api(app)
        api.add_resource(CodingAPI.CodeList,  '/getCodes/<game_id>')
        api.add_resource(CodingAPI.CoderList, '/getCoders/<game_id>')
        api.add_resource(CodingAPI.CodeCreate,'/createCode')

    class CoderList(Resource):
        def get(self, game_id:str):
            current_app.logger.info(f"Received request for {game_id} players.")
            ret_val = APIResult.Default(req_type=RESTType.GET)
            ret_val.RequestSucceeded(msg=f"SUCCESS: Got a (fake) list of codes for {game_id}", val=["Code1", "Code2", "Code3"])
            return ret_val.ToDict()

    class CodeList(Resource):
        def get(self, game_id:str):
            current_app.logger.info(f"Received request for {game_id} coders.")
            ret_val = APIResult.Default(req_type=RESTType.GET)
            ret_val.RequestSucceeded(msg=f"SUCCESS: Created a (fake) list of codes for {game_id}", val=["Code1", "Code2", "Code3"])
            return ret_val.ToDict()

    class CodeCreate(Resource):

        def post(self):

            # Step 1: get args
            parser = reqparse.RequestParser()
            parser.add_argument("game_id", type=str, required=True)
            parser.add_argument("player_id", type=str, required=False)
            parser.add_argument("session_id", type=str, required=True)
            parser.add_argument("code", type=str, required=True)
            parser.add_argument("indices", type=str, required=True, default="[]")
            parser.add_argument("coder",   type=str, required=True, default="default")
            parser.add_argument("notes",   type=str, required=False)
            args : Dict[str, Any] = parser.parse_args()

            game_id = args["game_id"]
            session_id = args["session_id"]
            code = args["code"]

            current_app.logger.info(f"Received request for {game_id} players.")
            ret_val = APIResult.Default(req_type=RESTType.POST)

            _indices = APIUtils.parse_list(args.get('indices') or "[]")
            _events = []
            if _indices is not None:
                _events = [Code.EventID(sess_id=session_id, index=idx) for idx in _indices]
            try:
                _success = False
                
                orig_cwd = os.getcwd()
                os.chdir(settings["OGD_CORE_PATH"])

                _interface : Optional[CodingInterface] = APIUtils.gen_coding_interface(game_id=game_id)
                if _interface is not None:
                    _success = _interface.CreateCode(code=code, coder_id=args.get('coder', "default"), events=_events, notes=args.get('notes', None))
                os.chdir(orig_cwd)
            except Exception as err:
                ret_val.ServerErrored(f"ERROR: {type(err).__name__} exception while processing Code request")
                current_app.logger.error(f"Got exception while processing Code request:\ngame={game_id}\n{str(err)}")
                current_app.logger.error(traceback.format_exc())
            else:
                if _success:
                    ret_val.RequestSucceeded(msg=f"SUCCESS: Added code with {len(_events)} events to database.", val=_success)
                else:
                    ret_val.RequestErrored(msg="FAIL: Unable to store code to database.")
                    ret_val.Value = _success
            return ret_val.ToDict()