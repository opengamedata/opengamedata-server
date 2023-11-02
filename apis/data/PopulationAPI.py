"""Module for the Population API code
"""
# import libraries
import os
import traceback
from datetime import datetime, timedelta
from flask import Flask
from flask import current_app
from flask_restful import Resource, Api, reqparse
from flask_restful.inputs import datetime_from_iso8601
from typing import Any, Dict, Optional
# import locals
from apis.APIResult import APIResult, RESTType, ResultStatus
from apis import APIUtils
from config.config import settings
from opengamedata.interfaces.DataInterface import DataInterface
from opengamedata.interfaces.outerfaces.DictionaryOuterface import DictionaryOuterface
from opengamedata.managers.ExportManager import ExportManager
from opengamedata.ogd_requests.Request import Request, ExporterRange
from opengamedata.ogd_requests.RequestResult import RequestResult
from opengamedata.schemas.ExportMode import ExportMode
from opengamedata.schemas.GameSchema import GameSchema

class PopulationAPI:
    """Class to define an API for the developer/designer dashboard"""
    @staticmethod
    def register(app:Flask):
        """Sets up the dashboard api in a flask app.

        :param app: _description_
        :type app: Flask
        """
        # Expected WSGIScriptAlias URL path is /data
        api = Api(app)
        api.add_resource(PopulationAPI.Population, '/populations/metrics')
        api.add_resource(PopulationAPI.PopulationFeatureList, '/populations/metrics/list/<game_id>')

    class Population(Resource):
        """Class for handling requests for population-level features."""
        def post(self):
            """Handles a POST request for population-level features.
            Gives back a dictionary of the APIResult, with the val being a dictionary of columns to values for the given population.

            :param game_id: _description_
            :type game_id: _type_
            :return: _description_
            :rtype: _type_
            """
            current_app.logger.info("Received population request.")
            ret_val = APIResult.Default(req_type=RESTType.POST)
            _end_time   : datetime = datetime.now()
            _start_time : datetime = _end_time-timedelta(hours=1)

            # TODO: figure out how to make this use the default and print "help" part to server log, or maybe append to return message, instead of sending back as the only response from the server and dying here.
            parser = reqparse.RequestParser()
            parser.add_argument("game_id", type=str, required=True)
            parser.add_argument("start_datetime", type=datetime_from_iso8601, required=False, default=_start_time, nullable=True, help="Invalid starting date, defaulting to 1 hour ago.")
            parser.add_argument("end_datetime",   type=datetime_from_iso8601, required=False, default=_end_time,   nullable=True, help="Invalid ending date, defaulting to present time.")
            parser.add_argument("metrics",        type=str,                   required=False, default="[]",        nullable=True, help="Got bad list of metrics, defaulting to all.")
            args : Dict[str, Any] = parser.parse_args()

            game_id = args["game_id"]

            _end_time   = args.get('end_datetime')   or _end_time
            _start_time = args.get('start_datetime') or _start_time
            _metrics    = APIUtils.parse_list(args.get('metrics') or "")

            try:
                result : RequestResult = RequestResult(msg="No Export")
                values_dict = {}
                
                orig_cwd = os.getcwd()
                os.chdir(settings["OGD_CORE_PATH"])

                _interface : Optional[DataInterface] = APIUtils.gen_interface(game_id=game_id)
                if _metrics is not None and _interface is not None:
                    _range     = ExporterRange.FromDateRange(source=_interface, date_min=_start_time, date_max=_end_time)
                    _exp_types = set([ExportMode.POPULATION])
                    _outerface = DictionaryOuterface(game_id=game_id, out_dict=values_dict)
                    request    = Request(range=_range,         exporter_modes=_exp_types,
                                         interface=_interface, outerfaces={_outerface},
                                         feature_overrides=_metrics
                    )
                    # retrieve and process the data
                    current_app.logger.info(f"Processing population request {request}...")
                    export_mgr = ExportManager(settings=settings)
                    result = export_mgr.ExecuteRequest(request=request)
                    current_app.logger.info(f"Result: {result.Message}")
                elif _metrics is None:
                    current_app.logger.warning("_metrics was None")
                elif _interface is None:
                    current_app.logger.warning("_interface was None")
                os.chdir(orig_cwd)
            except Exception as err:
                ret_val.ServerErrored(f"Unknown error while processing Population request")
                current_app.logger.error(f"Got exception for Population request:\ngame={game_id}\n{str(err)}\n{traceback.format_exc()}")
            else:
                current_app.logger.info(f"The values_dict:\n{values_dict}")
                cols = values_dict.get("populations", {}).get("cols", [])
                pop  = values_dict.get("populations", {}).get("vals", [[]])[0]
                ct = min(len(cols), len(pop))
                if ct > 0:
                    ret_val.RequestSucceeded(
                        msg="Generated population features",
                        val={cols[i] : pop[i] for i in range(ct)}
                    )
                else:
                    ret_val.RequestErrored("No valid population features")
            return ret_val.ToDict()

    class PopulationFeatureList(Resource):
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