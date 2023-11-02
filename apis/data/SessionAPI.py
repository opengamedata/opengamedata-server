"""Module for the Session API code
"""
# import libraries
import os
import traceback
from datetime import datetime, timedelta
from flask import Flask
from flask import current_app
from flask_restful import Resource, Api, reqparse
from flask_restful.inputs import datetime_from_iso8601
from typing import Optional, Union
# import locals
from apis.APIResult import APIResult, RESTType, ResultStatus
from apis import APIUtils
from config.config import settings
from opengamedata.interfaces.DataInterface import DataInterface
from opengamedata.interfaces.outerfaces.DictionaryOuterface import DictionaryOuterface
from opengamedata.managers.ExportManager import ExportManager
from opengamedata.ogd_requests.Request import Request, ExporterRange, IDMode
from opengamedata.ogd_requests.RequestResult import RequestResult
from opengamedata.schemas.ExportMode import ExportMode
from opengamedata.schemas.GameSchema import GameSchema

class SessionAPI:
    """Class to define an API for the developer/designer dashboard"""
    @staticmethod
    def register(app:Flask):
        """Sets up the dashboard api in a flask app.

        :param app: _description_
        :type app: Flask
        """
        # Expected WSGIScriptAlias URL path is /data
        api = Api(app)
        api.add_resource(SessionAPI.SessionList, '/sessions/list/<game_id>')
        api.add_resource(SessionAPI.SessionsMetrics, '/sessions/metrics')
        api.add_resource(SessionAPI.SessionMetrics, '/session/metrics')
        api.add_resource(SessionAPI.SessionFeatureList, '/sessions/metrics/list/<game_id>')

    
    class SessionList(Resource):
        """Class for handling requests for a list of sessions over a date range."""
        def get(self, game_id):
            """Handles a GET request for a list of sessions.

            :param game_id: _description_
            :type game_id: _type_
            :return: _description_
            :rtype: _type_
            """
            current_app.logger.info("Received session list request.")
            ret_val = APIResult.Default(req_type=RESTType.GET)

            _end_time   : datetime = datetime.now()
            _start_time : datetime = _end_time-timedelta(hours=1)

            parser = reqparse.RequestParser()
            parser.add_argument("start_datetime", type=datetime_from_iso8601, required=False, default=_start_time, nullable=True, help="Invalid starting date, defaulting to 1 hour ago.", location="args")
            parser.add_argument("end_datetime",   type=datetime_from_iso8601, required=False, default=_end_time,   nullable=True, help="Invalid ending date, defaulting to present time.", location="args")
            args = parser.parse_args()

            _end_time   = args.get('end_datetime')   or _end_time
            _start_time = args.get('start_datetime') or _start_time
            _range : Union[ExporterRange, None] = None
            try:
                
                orig_cwd = os.getcwd()
                os.chdir(settings["OGD_CORE_PATH"])

                _interface : Union[DataInterface, None] = APIUtils.gen_interface(game_id=game_id)
                if _interface is not None:
                    _range = ExporterRange.FromDateRange(source=_interface, date_min=_start_time, date_max=_end_time)
                os.chdir(orig_cwd)
            except Exception as err:
                ret_val.ServerErrored(f"ERROR: {type(err).__name__} error while processing SessionList request")
                current_app.logger.error(f"Got exception for SessionList request:\ngame={game_id}\n{str(err)}")
                current_app.logger.error(traceback.format_exc())
            else:
                if _range is not None:
                    ret_val.RequestSucceeded(msg="SUCCESS: Got ID list for given date range", val=_range.IDs)
                else:
                    ret_val.RequestErrored("FAIL: Did not find IDs in the given date range")
            return ret_val.ToDict()

    class SessionsMetrics(Resource):
        """Class for handling requests for session-level features, given a list of session ids."""
        def post(self):
            """Handles a POST  request for session-level features for a list of sessions.

            :param game_id: _description_
            :type game_id: _type_
            :return: _description_
            :rtype: _type_
            """
            current_app.logger.info("Received sessions request.")
            ret_val = APIResult.Default(req_type=RESTType.POST)

            parser = reqparse.RequestParser()
            parser.add_argument("game_id", type=str, required=True)
            parser.add_argument("session_ids", type=str, required=False, default="[]", nullable=True, help="Got bad list of session ids, defaulting to [].")
            parser.add_argument("metrics",    type=str, required=False, default="[]", nullable=True, help="Got bad list of metrics, defaulting to all.")
            args = parser.parse_args()

            game_id = args["game_id"]

            _metrics     = APIUtils.parse_list(args.get('metrics') or "")
            _session_ids = APIUtils.parse_list(args.get('session_ids') or "[]")
            try:
                result : RequestResult = RequestResult(msg="Empty result")
                values_dict = {}
                
                orig_cwd = os.getcwd()
                os.chdir(settings["OGD_CORE_PATH"])

                _interface : Union[DataInterface, None] = APIUtils.gen_interface(game_id=game_id)
                if _metrics is not None and _session_ids is not None and _interface is not None:
                    _range = ExporterRange.FromIDs(source=_interface, ids=_session_ids, id_mode=IDMode.SESSION)
                    _exp_types = set([ExportMode.SESSION])
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
                ret_val.ServerErrored(f"ERROR: {type(err).__name__} error while processing Sessions request")
                current_app.logger.error(f"Got exception for Sessions request:\ngame={game_id}\n{str(err)}")
                current_app.logger.error(traceback.format_exc())
            else:
                val = values_dict.get("sessions")
                if val is not None:
                    ret_val.RequestSucceeded(
                        msg="SUCCESS: Generated features for given sessions",
                        val=val
                    )
                else:
                    current_app.logger.debug(f"Couldn't find anything in result[sessions], result was:\n{result}")
                    ret_val.RequestErrored("FAIL: No valid session features")
            return ret_val.ToDict()
    
    class SessionMetrics(Resource):
        """Class for handling requests for session-level features, given a session id."""
        def post(self):
            """Handles a GET request for session-level features of a single Session.
            Gives back a dictionary of the APIResult, with the val being a dictionary of columns to values for the given session.

            :param game_id: _description_
            :type game_id: _type_
            :param session_id: _description_
            :type session_id: _type_
            :return: _description_
            :rtype: _type_
            """
            current_app.logger.info("Received session request.")
            ret_val = APIResult.Default(req_type=RESTType.GET)

            parser = reqparse.RequestParser()
            parser.add_argument("game_id", type=str, required=True)
            parser.add_argument("session_id", type=str, required=True)
            parser.add_argument("metrics", type=str, required=False, default="[]", nullable=True, help="Got bad list of metrics, defaulting to all.")
            args = parser.parse_args()

            game_id = args["game_id"]
            session_id = args["session_id"]

            _metrics    = APIUtils.parse_list(args.get('metrics') or "")
            try:
                result : RequestResult = RequestResult(msg="Empty result")
                values_dict = {}
                
                orig_cwd = os.getcwd()
                os.chdir(settings["OGD_CORE_PATH"])

                _interface : Optional[DataInterface] = APIUtils.gen_interface(game_id=game_id)
                if _metrics is not None and _interface is not None:
                    _range = ExporterRange.FromIDs(source=_interface, ids=[session_id], id_mode=IDMode.SESSION)
                    _exp_types = set([ExportMode.SESSION])
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
                ret_val.ServerErrored(f"ERROR: {type(err).__name__} error while processing Session request")
                current_app.logger.error(f"Got exception for Session request:\ngame={game_id}, player={session_id}\n{str(err)}")
                current_app.logger.error(traceback.format_exc())
            else:
                cols = values_dict.get("sessions", {}).get("cols", [])
                sessions = values_dict.get("sessions", {}).get("vals", [[]])
                sess = self._findSession(session_list=sessions, target_id=session_id)
                ct = min(len(cols), len(sess))
                if ct > 0:
                    ret_val.RequestSucceeded(
                        msg="SUCCESS: Generated features for the given session",
                        val={cols[i] : sess[i] for i in range(ct)}
                    )
                else:
                    current_app.logger.debug(f"Couldn't find anything in result[session], result was:\n{result}")
                    ret_val.RequestErrored("FAIL: No valid session features")
            return ret_val.ToDict()

        def _findSession(self, session_list, target_id):
            ret_val = None
            for _session in session_list:
                _session_id = _session[0]
                if _session_id == target_id:
                    ret_val = _session
            if ret_val is None:
                current_app.logger.warn(f"Didn't find {target_id} in list of session results, defaulting to first session in list (session ID={session_list[0][0]})")
                ret_val = session_list[0]
            return ret_val

    class SessionFeatureList(Resource):
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