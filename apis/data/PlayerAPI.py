"""Module for the Player API code
"""
# import libraries
import os
import traceback
from datetime import datetime, timedelta
from flask import Flask, current_app
from flask_restful import Resource, Api, reqparse
from flask_restful.inputs import datetime_from_iso8601
from typing import Any, Dict, Optional, Union
# import locals
from apis.APIResult import APIResult, RESTType, ResultStatus
from apis import APIUtils
from config.config import settings
from opengamedata.interfaces.DataInterface import DataInterface
from opengamedata.interfaces.outerfaces.DictionaryOuterface import DictionaryOuterface
from opengamedata.managers.ExportManager import ExportManager
from opengamedata.schemas.GameSchema import GameSchema
from opengamedata.schemas.IDMode import IDMode
from opengamedata.schemas.ExportMode import ExportMode
from opengamedata.ogd_requests.Request import Request, ExporterRange
from opengamedata.ogd_requests.RequestResult import RequestResult
class PlayerAPI:
    """Class to define an API for the developer/designer dashboard"""
    @staticmethod
    def register(app:Flask):
        """Sets up the dashboard api in a flask app.

        :param app: _description_
        :type app: Flask
        """
        # Expected WSGIScriptAlias URL path is /data
        api = Api(app)
        api.add_resource(PlayerAPI.PlayerList, '/players/list/<game_id>')
        api.add_resource(PlayerAPI.PlayersMetrics, '/players/metrics')
        api.add_resource(PlayerAPI.PlayerMetrics, '/player/metrics')
        api.add_resource(PlayerAPI.PlayerFeatureList, '/players/metrics/list/<game_id>')

    class PlayerList(Resource):
        """Class for handling requests for a list of sessions over a date range."""
        def get(self, game_id):
            """Handles a GET request for a list of sessions.

            :param game_id: _description_
            :type game_id: _type_
            :return: _description_
            :rtype: _type_
            """
            current_app.logger.info(f"Received request for {game_id} player list.")
            ret_val = APIResult.Default(req_type=RESTType.GET)

            _end_time   : datetime = datetime.now()
            _start_time : datetime = _end_time-timedelta(hours=1)

            parser = reqparse.RequestParser()
            parser.add_argument("start_datetime", type=datetime_from_iso8601, required=False, default=_start_time, nullable=True, help="Invalid starting date, defaulting to 1 hour ago.", location="args")
            parser.add_argument("end_datetime",   type=datetime_from_iso8601, required=False, default=_end_time,   nullable=True, help="Invalid ending date, defaulting to present time.", location="args")
            args : Dict[str, Any] = parser.parse_args()

            _end_time   = args.get('end_datetime')   or _end_time
            _start_time = args.get('start_datetime') or _start_time

            try:
                result = {}
                orig_cwd = os.getcwd()
                os.chdir(settings["OGD_CORE_PATH"])
                _interface : Union[DataInterface, None] = APIUtils.gen_interface(game_id=game_id)
                if _interface is not None:
                    _range = ExporterRange.FromDateRange(source=_interface, date_min=_start_time, date_max=_end_time)
                    result["ids"] = _range.IDs
                os.chdir(orig_cwd)
            except Exception as err:
                ret_val.ServerErrored(f"ERROR: {type(err).__name__} error while processing PlayerList request")
                current_app.logger.error(f"Got exception for PlayerList request:\ngame={game_id}\n{str(err)}")
                current_app.logger.error(traceback.format_exc())
            else:
                val = result.get('ids')
                if val is not None:
                    ret_val.RequestSucceeded(msg="SUCCESS: Got ID list for given date range", val=val)
                else:
                    ret_val.RequestErrored("FAIL: Did not find IDs in the given date range")
            return ret_val.ToDict()

    class PlayersMetrics(Resource):
        """Class for handling requests for session-level features, given a list of session ids."""
        def post(self):
            """Handles a GET request for session-level features for a list of sessions.

            :param game_id: _description_
            :type game_id: _type_
            :return: _description_
            :rtype: _type_
            """
            
            ret_val = APIResult.Default(req_type=RESTType.GET)
            parser = reqparse.RequestParser()
            parser.add_argument("game_id", type=str, required=True)
            parser.add_argument("player_ids", type=str, required=False, default="[]", nullable=True, help="Got bad list of player ids, defaulting to [].")
            parser.add_argument("metrics",    type=str, required=False, default="[]", nullable=True, help="Got bad list of metrics, defaulting to all.")
            args = parser.parse_args()

            game_id = args["game_id"]
            
            current_app.logger.info(f"Received request for {game_id} players.")

            _metrics    = APIUtils.parse_list(args.get('metrics') or "")
            _player_ids = APIUtils.parse_list(args.get('player_ids') or "[]")
            try:
                result : RequestResult = RequestResult(msg="Empty result")
                values_dict = {}

                orig_cwd = os.getcwd()
                os.chdir(settings["OGD_CORE_PATH"])

                _interface : Optional[DataInterface] = APIUtils.gen_interface(game_id=game_id)
                if _metrics is not None and _player_ids is not None and _interface is not None:
                    _range     = ExporterRange.FromIDs(source=_interface, ids=_player_ids, id_mode=IDMode.USER)
                    _exp_types = set([ExportMode.PLAYER])
                    _outerface = DictionaryOuterface(game_id=game_id, out_dict=values_dict)
                    request    = Request(interface=_interface,      range=_range,
                                         exporter_modes=_exp_types, outerfaces={_outerface},
                                         feature_overrides=_metrics
                    )
                    # retrieve and process the data
                    export_mgr = ExportManager(settings=settings)
                    result = export_mgr.ExecuteRequest(request=request)
                elif _metrics is None:
                    current_app.logger.warning("_metrics was None")
                elif _interface is None:
                    current_app.logger.warning("_interface was None")
                os.chdir(orig_cwd)

            except Exception as err:
                ret_val.ServerErrored(f"ERROR: {type(err).__name__} error while processing Players request")
                current_app.logger.error(f"Got exception for Players request:\ngame={game_id}\n{str(err)}")
                current_app.logger.error(traceback.format_exc())
            else:
                val = values_dict.get("players")
                if val is not None:
                    ret_val.RequestSucceeded(
                        msg="SUCCESS: Generated features for given sessions",
                        val=val
                    )
                else:
                    current_app.logger.debug(f"Couldn't find anything in result[players], result was:\n{result}")
                    ret_val.RequestErrored("FAIL: No valid session features")
            return ret_val.ToDict()
    
    class PlayerMetrics(Resource):
        """Class for handling requests for session-level features, given a session id."""
        def post(self):
            """Handles a GET request for session-level features of a single Session.
            Gives back a dictionary of the APIResult, with the val being a dictionary of columns to values for the given player.

            :param game_id: _description_
            :type game_id: _type_
            :param player_id: _description_
            :type player_id: _type_
            :return: _description_
            :rtype: _type_
            """
            ret_val = APIResult.Default(req_type=RESTType.GET)

            parser = reqparse.RequestParser()
            parser.add_argument("game_id", type=str, required=True)
            parser.add_argument("player_id", type=str, required=True)
            parser.add_argument("metrics", type=str, required=False, default="[]", nullable=True, help="Got bad list of metrics, defaulting to all.")
            args : Dict[str, Any] = parser.parse_args()

            game_id = args["game_id"]
            player_id = args["player_id"]

            current_app.logger.info(f"Received request for {game_id} player {player_id}.")
            current_app.logger.debug(f"Unparsed 'metrics' list from args: {args.get('metrics')}")

            _metrics = APIUtils.parse_list(args.get('metrics') or "")
            try:
                result : RequestResult = RequestResult(msg="Empty result")
                values_dict = {}
                
                orig_cwd = os.getcwd()
                os.chdir(settings["OGD_CORE_PATH"])

                _interface : Optional[DataInterface] = APIUtils.gen_interface(game_id=game_id)
                if _metrics is not None and _interface is not None:
                    _range = ExporterRange.FromIDs(source=_interface, ids=[player_id], id_mode=IDMode.USER)
                    _exp_types = set([ExportMode.PLAYER])
                    _outerface = DictionaryOuterface(game_id=game_id, out_dict=values_dict)
                    request    = Request(interface=_interface,      range=_range,
                                         exporter_modes=_exp_types, outerfaces={_outerface},
                                         feature_overrides=_metrics
                    )
                    # retrieve and process the data
                    export_mgr = ExportManager(settings=settings)
                    result = export_mgr.ExecuteRequest(request=request)
                elif _metrics is None:
                    current_app.logger.warning("_metrics was None")
                elif _interface is None:
                    current_app.logger.warning("_interface was None")
                os.chdir(orig_cwd)
            except Exception as err:
                ret_val.ServerErrored(f"ERROR: {type(err).__name__} error while processing Player request")
                current_app.logger.error(f"Got exception for Player request:\ngame={game_id}, player={player_id}\nerror={str(err)}")
                current_app.logger.error(traceback.format_exc())
            else:
                cols   = values_dict.get("players", {}).get("cols", [])
                players = values_dict.get("players", {}).get("vals", [[]])
                player = self._findPlayer(player_list=players, target_id=player_id)
                ct = min(len(cols), len(player))
                if ct > 0:
                    ret_val.RequestSucceeded(
                        msg="SUCCESS: Generated features for the given session",
                        val={cols[i] : player[i] for i in range(ct)}
                    )
                else:
                    current_app.logger.warn(f"Couldn't find anything in result[player], result was:\n{result}")
                    ret_val.RequestErrored("FAIL: No valid session features")
            return ret_val.ToDict()

        def _findPlayer(self, player_list, target_id):
            ret_val = None
            for _player in player_list:
                _player_id = _player[0]
                if _player_id == target_id:
                    ret_val = _player
            if ret_val is None:
                current_app.logger.warn(f"Didn't find {target_id} in list of player results, defaulting to first player in list (player ID={player_list[0][0]})")
                ret_val = player_list[0]
            return ret_val

    class PlayerFeatureList(Resource):
        """Class for getting a full list of features for a given game."""
        def get(self, game_id):
            """Handles a GET request for a list of sessions.

            :param game_id: _description_
            :type game_id: _type_
            :return: _description_
            :rtype: _type_
            """
            print("Received metric list request.")
            ret_val = APIResult.Default(req_type=RESTType.GET)

            try:
                feature_list = []
                
                orig_cwd = os.getcwd()
                os.chdir(settings["OGD_CORE_PATH"])

                _schema = GameSchema(schema_name=f"{game_id}.json")
                for name,percount in _schema.PerCountFeatures.items():
                    if percount.get('enabled', False):
                        feature_list.append(name)
                for name,aggregate in _schema.AggregateFeatures.items():
                    if aggregate.get('enabled', False):
                        feature_list.append(name)
                os.chdir(orig_cwd)
            except Exception as err:
                ret_val.ServerErrored(f"ERROR: Unknown error while processing FeatureList request")
                print(f"Got exception for FeatureList request:\ngame={game_id}\n{str(err)}")
                print(traceback.format_exc())
            else:
                if feature_list != []:
                    ret_val.RequestSucceeded(msg="SUCCESS: Got metric list for given game", val=feature_list)
                else:
                    ret_val.RequestErrored("FAIL: Did not find any metrics for the given game")
            return ret_val.ToDict()