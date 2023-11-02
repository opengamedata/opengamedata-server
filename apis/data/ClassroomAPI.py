# import libraries
import uuid
from os import stat
from flask import Flask, session
from flask_restful import reqparse, Api, Resource
from google.oauth2 import id_token
from google.auth.transport import requests
from google.auth.exceptions import GoogleAuthError
from mysql.connector import Error as MySQLError
from mysql.connector.connection import MySQLConnection
from typing import Any, Dict, Union
# import locals
from config.config import settings
from opengamedata.interfaces.MySQLInterface import SQL

class ClassroomAPI:
    @staticmethod
    def register(app:Flask):
        # Expected WSGIScriptAlias URL path is /data
        api = Api(app)
        api.add_resource(ClassroomAPI.TeacherLogin, '/classrooms/login')
        api.add_resource(ClassroomAPI.Teacher, '/classrooms/teacherInfo')
        api.add_resource(ClassroomAPI.ClassroomInfo, '/classrooms/classInfo/<class_id>')
        api.add_resource(ClassroomAPI.ClassroomAssignTeacher, '/classrooms/assign/teacher')
        api.add_resource(ClassroomAPI.ClassroomStudentInfo, '/classrooms/studentInfo/<player_id>')
        api.add_resource(ClassroomAPI.ClassroomAssignStudent, '/classrooms/assign/student')

    class TeacherLogin(Resource):
        @staticmethod
        def _verifyToken(token) -> Union[str, None]:
            try:
                ret_val = id_token.verify_oauth2_token(token, requests.Request(), settings["GOOGLE_CLIENT_ID"])
                # If auth request is from a G Suite domain:
                # if idinfo['hd'] != GSUITE_DOMAIN_NAME:
                #     raise ValueError('Wrong hosted domain.')
            except GoogleAuthError:
                return None
            except ValueError:
                # Invalid token
                return None
            else:
                # ID token is valid. Get the user's Google Account ID from the decoded token.
                return ret_val
        
        @staticmethod
        def _unusedID(db_conn:Union[MySQLConnection, None], db_name:str, teacher_id:Union[str,None]) -> bool:
            ret_val = False
            if db_conn is not None and teacher_id is not None:
                try:
                    query = f"SELECT COUNT(*) FROM {db_name}.teacher_codes WHERE `teacher_id`=%s;"
                    params = (teacher_id,)
                    count = SQL.Query(cursor=db_conn.cursor(), query=query, params=params, fetch_results=True)
                except MySQLError as err:
                    print(f"ERROR: Could not complete query to check if ID is unused, got error {err}")
                else:
                    # print(f"GOT COUNT: {count}")
                    if count is not None and count[0][0] == 0:
                        return True
            return ret_val

        @staticmethod
        def _createTeacher(db_conn:Union[MySQLConnection, None], db_name:str, id_token) -> Union[str,None]:
            ret_val = None
            if db_conn is not None:
                count = 0
                id = None
                while (not ClassroomAPI.TeacherLogin._unusedID(db_conn=db_conn, db_name=db_name, teacher_id=id)) and (count < 1000):
                    id = uuid.uuid4().hex
                    count += 1
                try:
                    query_string = f"""INSERT INTO {db_name}.teacher_codes (`teacher_id`, `given_name`, `family_name`, `email`, `google_sub`)
                                    VALUES (%s, %s, %s, %s, %s)"""
                    given_name  = id_token["given_name"] if "given_name" in id_token.keys() else None
                    family_name = id_token["family_name"] if "family_name" in id_token.keys() else None
                    email       = id_token["email"] if "email" in id_token.keys() else None
                    query_params = (id, given_name, family_name, email, id_token['sub'], )
                    SQL.Query(cursor=db_conn.cursor(), query=query_string, params=query_params, fetch_results=False)
            # Step 3: process and return states
                except MySQLError as err:
                    print(f"ERROR: Could not complete query, got error {err}")
                else:
                    ret_val = id
                finally:
                    SQL.disconnectMySQL(db_conn)
            return ret_val
        
        @staticmethod
        def _retrieveTeacher(db_conn:Union[MySQLConnection, None], db_name:str, id_token) -> Union[str, None]:
            ret_val = None
            # Step 1: Try to get teacher_id
            if db_conn is not None and id_token is not None:
                try:
                    query_string = f"""SELECT `teacher_id` from {db_name}.teacher_codes WHERE `google_sub`=%s LIMIT 1;"""
                    query_params = (id_token['sub'],)
                    teacher_id = SQL.Query(cursor=db_conn.cursor(), query=query_string, params=query_params, fetch_results=True)
                except MySQLError as err:
                    print(f"ERROR: Could not complete query, got error {err}")
            # Step 2: process and return teacher_id.
                else:
                    if teacher_id is not None and len(teacher_id) == 1:
                        ret_val = teacher_id[0][0]
                    elif teacher_id is not None and len(teacher_id) == 0:
                        print(f"ERROR: Could not retrieve teacher")
                    else:
                        print(f"ERROR: Somehow got multiple instances of teacher")
                finally:
                    SQL.disconnectMySQL(db_conn)
            return ret_val

        @staticmethod
        def _updateTeacher(db_conn:Union[MySQLConnection, None], db_name:str, id_token) -> bool:
            ret_val = False
            if db_conn is not None:
                try:
                    query_string = f"""UPDATE {db_name}.teacher_codes
                                    SET `given_name`=%s, `family_name`=%s, `email`=%s
                                    WHERE `google_sub`=%s"""
                    given_name   = id_token["given_name"] if "given_name" in id_token.keys() else None
                    family_name  = id_token["family_name"] if "family_name" in id_token.keys() else None
                    email        = id_token["email"] if "email" in id_token.keys() else None
                    query_params = (given_name, family_name, email, id_token['sub'])
                    teacher_id   = SQL.Query(cursor=db_conn.cursor(), query=query_string, params=query_params, fetch_results=True)
            # Step 3: process and return states
                except MySQLError as err:
                    print(f"ERROR: Could not complete query, got error {err}")
                else:
                    ret_val = teacher_id[0][0]
                finally:
                    SQL.disconnectMySQL(db_conn)
            return ret_val
        
        def post(self):
            ret_val : Dict[str,Any] = {
                "type":"POST",
                "val":None,
                "msg":"",
                "status":"SUCCESS",
            }
            # Step 1: Get args and check token is valid
            parser = reqparse.RequestParser()
            parser.add_argument("token")
            parser.add_argument("teacher_id")
            args = parser.parse_args()

            id_token = ClassroomAPI.TeacherLogin._verifyToken(args["token"])
            teacher_id = args["teacher_id"]

            if id_token is not None:
            # Step 2: If token is valid, update database with whatever data we got
                fd_config = settings["DB_CONFIG"]["fd_users"]
                _dummy, db_conn = SQL.ConnectDB(db_settings=fd_config)
                teacher_id = ClassroomAPI.TeacherLogin._retrieveTeacher(db_conn=db_conn, db_name=fd_config["DB_NAME"], id_token=id_token)
                if teacher_id is None:
                    teacher_id = ClassroomAPI.TeacherLogin._createTeacher(db_conn=db_conn, db_name=fd_config["DB_NAME"], id_token=id_token)
                else:
                    ClassroomAPI.TeacherLogin._updateTeacher(db_conn=db_conn, db_name=fd_config["DB_NAME"], id_token=id_token)
            # Step 3: Mark teacher as having a session
                if teacher_id is not None:
                    session["teacher_id"] = teacher_id
                    ret_val["msg"] = f"SUCCESS: Teacher {teacher_id} is now logged in"
                else:
                    ret_val["msg"] = "FAIL: Could not retrieve the teacher's id"
                    ret_val['status'] = "ERR_DB"
            else:
                ret_val["message"] = "FAIL: Could not verify the teacher's Google Login"
                ret_val['status'] = "ERR_SRV"
            return ret_val

    class Teacher(Resource):
        @staticmethod
        def _hasClassroom(db_conn:Union[MySQLConnection, None], db_name:str, teacher_id:Union[str,None], class_id:str) -> bool:
            ret_val : bool = False
            if db_conn is not None:
                try:
                    teacher_query = f"""SELECT COUNT(*) from {db_name}.teacher_classrooms
                                        WHERE `teacher_id`=%s AND `class_id`=%s;"""
                    teacher_params = (teacher_id, class_id)
                    teacher_has_classroom = SQL.Query(cursor=db_conn.cursor(), query=teacher_query, params=teacher_params, fetch_results=True)
                except MySQLError as err:
                    print(f"ERROR: Could not complete query, got error {err}")
                else:
                    if teacher_has_classroom is not None and teacher_has_classroom[0][0] != 0: # in this case, teacher_id and class_id match together
                        ret_val = True
            return ret_val

        @staticmethod
        def _hasStudent(db_conn:Union[MySQLConnection, None], db_name:str, teacher_id:Union[str,None], student_id:str) -> bool:
            ret_val : bool = False
            if db_conn is not None:
                try:
                    teacher_query = f"""SELECT COUNT({db_name}.player_classrooms.player_id) from {db_name}.teacher_classrooms
                                        INNER JOIN {db_name}.player_classrooms ON {db_name}.teacher_classrooms.class_id = {db_name}.player_classrooms.class_id
                                        WHERE `teacher_id`=%s AND `player_id`=%s;"""
                    teacher_params = (teacher_id, student_id)
                    teacher_has_student = SQL.Query(cursor=db_conn.cursor(), query=teacher_query, params=teacher_params, fetch_results=True)
                except MySQLError as err:
                    print(f"ERROR: Could not complete query, got error {err}")
                else:
                    if teacher_has_student is not None and teacher_has_student[0][0] != 0: # in this case, teacher_id and student_id match together
                        ret_val = True
            return ret_val

        def get(self):
            ret_val : Dict[str,Any] = {
                "type":"GET",
                "val":None,
                "msg":"",
                "status":"SUCCESS",
            }

            # If teacher has authenticated
            if "teacher_id" in session:

                teacher_id = session["teacher_id"]

                # Step 1: Set up database and get the teacher info
                fd_config = settings["DB_CONFIG"]["fd_users"]
                _dummy, db_conn = SQL.ConnectDB(db_settings=fd_config)
                try:
                    teacher_query = f"""SELECT `given_name`, `family_name`, `email` from {fd_config['DB_NAME']}.teacher_codes
                                    WHERE `teacher_id`=%s LIMIT 1;"""
                    classroom_query = f"""SELECT `class_id` from {fd_config['DB_NAME']}.teacher_classrooms
                                    WHERE `teacher_id`=%s LIMIT 1;"""
                    params = (teacher_id,)
                    teacher_data = SQL.Query(cursor=db_conn.cursor(), query=teacher_query, params=params, fetch_results=True)
                    classroom_data = SQL.Query(cursor=db_conn.cursor(), query=classroom_query, params=params, fetch_results=True)
                # Step 2: process and return data
                except MySQLError as err:
                    print(f"ERROR: Could not complete query, got error {err}")
                    ret_val['msg'] = "FAIL: Could not retrieve the teacher's data"
                    ret_val['status'] = "ERR_DB"
                else:
                    given_name = teacher_data[0][0]
                    family_name = teacher_data[0][1]
                    email = teacher_data[0][2]
                    classrooms = [classroom[0] for classroom in classroom_data]
                    ret_val['val'] = { "given_name":given_name, "family_name":family_name, "email":email, "classrooms":classrooms }
                    ret_val['msg'] = f"SUCCESS: Retrieved data for {teacher_id}"
                finally:
                    SQL.disconnectMySQL(db_conn)
            else:
                ret_val['msg'] = f"FAIL: Could not get teacher info, teacher is not logged in"
                ret_val['status'] = "ERR_REQ"
            return ret_val
        
        # def post(self, teacher_id):
        #     ret_val = {"message":""}
        #     parser = reqparse.RequestParser()
        #     parser.add_argument("token")
        #     args = parser.parse_args()
        #     id_info = ClassroomAPI.Teacher._verifyTeacher(args["token"])
        #     if id_info is not None:
        #         session["teacher_id"] = teacher_id
        #         ret_val["message"] = f"SUCCESS: Teacher {teacher_id} is now logged in"
        #     else:
        #         ret_val["message"] = "FAIL: Could not verify the teacher's Google Login"
        #     return ret_val


    class ClassroomInfo(Resource):
        def get(self, class_id):
            ret_val : Dict[str,Any] = {
                "val":None,
                "msg":"",
                "status":"SUCCESS",
            }

            # Step 1: Get args and set up database

            # If teacher has authenticated
            if "teacher_id" in session:
                teacher_id = session["teacher_id"]
                fd_config = settings["DB_CONFIG"]["fd_users"]
                _dummy, db_conn = SQL.ConnectDB(db_settings=fd_config)
            # Step 2: If teacher has the classroom, we can retrieve the list of students.
                if db_conn is not None and ClassroomAPI.Teacher._hasClassroom(db_conn=db_conn, db_name=fd_config["DB_NAME"], teacher_id=teacher_id, class_id=class_id):
                    try:
                        players_query = f"""SELECT `player_id` from {fd_config['DB_NAME']}.player_classrooms
                                        WHERE `class_id`=%s LIMIT 1;"""
                        players_params = (class_id,)
                        players_data = SQL.Query(cursor=db_conn.cursor(), query=players_query, params=players_params, fetch_results=True)
                    except MySQLError as err:
                        ret_val['msg'] = "FAIL: Could not retrieve the classroom data, a database occurred"
                        ret_val['status'] = "ERR_DB"
                    else:
            # Step 3: process and return data
                        ret_val['val'] = [player[0] for player in players_data]
                        ret_val['msg'] = f"SUCCESS: Retrieved data for classroom {class_id}"
                SQL.disconnectMySQL(db_conn)
            else:
                ret_val['msg'] = f"FAIL: Could not retreive the classroom data, teacher is not logged in"
                ret_val['status'] = "ERR_REQ"
            return ret_val

    # This is for teachers to assign themselves or a secondary teacher to a classroom
    class ClassroomAssignTeacher(Resource):
        def post(self):
            ret_val : Dict[str,Any] = {
                "val":None,
                "msg":"",
                "status":"SUCCESS",
            }
            # Step 1: Get args and set up database
            parser = reqparse.RequestParser()
            parser.add_argument("teacher_id")
            parser.add_argument("class_id")
            args = parser.parse_args()
            teacher_id = args["teacher_id"]
            class_id = args["class_id"]

            # TODO:
            
            # If class_id is empty/null, we'll create a class and return the class_id
            
            # If a class_id and teacher_id is given, assume the logged-in teacher is assigning
            # a second teacher (assistant) to the class. Confirm the logged-in teacher is already 
            # associated with the class before assigning the second teacher            


            if "teacher_id" in session and (session['teacher_id'] == teacher_id):
                fd_config = settings["DB_CONFIG"]["fd_users"]
                _dummy, db_conn = SQL.ConnectDB(db_settings=fd_config)
            # Step 2: If teacher does not have the classroom, we can add it.
                if (db_conn is not None) and (not ClassroomAPI.Teacher._hasClassroom(db_conn=db_conn, db_name=fd_config["DB_NAME"], teacher_id=teacher_id, class_id=class_id)):
                    try:
                        query_string = f"""INSERT INTO {fd_config['DB_NAME']}.teacher_classrooms
                                           (teacher_id, class_id)
                                           VALUES (%s, %s);"""
                        params = (teacher_id, class_id)
                        SQL.Query(cursor=db_conn.cursor(), query=query_string, params=params, fetch_results=False)
                    except MySQLError as err:
                        ret_val['msg'] = "FAIL: Could not create the classroom, a database error occurred."
                        ret_val['status'] = "ERR_DB"
                    else:
            # Step 3: process and return data
                        ret_val['msg'] = f"SUCCESS: Created classroom {class_id}"
                    finally:
                        SQL.disconnectMySQL(db_conn)
                else:
                    ret_val['msg'] = f"FAIL: Teacher does not have access to the classroom"
                    ret_val['status'] = "ERR_REQ"
            else:
                ret_val['msg'] = f"FAIL: Could not create classroom, teacher is not logged in"
                ret_val['status'] = "ERR_REQ"
            return ret_val

    class ClassroomStudentInfo(Resource):
        @staticmethod
        def _hasClassroom(db_conn:Union[MySQLConnection, None], db_name:str, student_id:Union[str,None], class_id:str) -> bool:
            ret_val : bool = False
            if db_conn is not None:
                try:
                    query_string = f"""SELECT COUNT(*) from {db_name}.player_classrooms
                                        WHERE `player_id`=%s AND `class_id`=%s;"""
                    params = (student_id, class_id)
                    student_has_classroom = SQL.Query(cursor=db_conn.cursor(), query=query_string, params=params, fetch_results=True)
                except MySQLError as err:
                    print(f"ERROR: Could not complete query, got error {err}")
                else:
                    if student_has_classroom[0][0] != 0: # in this case, teacher_id and class_id match together
                        ret_val = True
            return ret_val

        def get(self, player_id):
            ret_val : Dict[str,Any] = {
                "val":None,
                "msg":"",
                "status":"SUCCESS",
            }
            # Step 1: get args and set up database.

            # If teacher has authenticated
            if "teacher_id" in session:
                teacher_id = session["teacher_id"]
                fd_config = settings["DB_CONFIG"]["fd_users"]
                _dummy, db_conn = SQL.ConnectDB(db_settings=fd_config)
                # Step 2: If teacher has student, then we can retrieve their name.
                if db_conn is not None and ClassroomAPI.Teacher._hasStudent(db_conn=db_conn, db_name=fd_config["DB_NAME"], teacher_id=args["teacher_id"], student_id=player_id):
                    try:
                        db_name = fd_config['DB_NAME']
                        query_string = f"""SELECT {db_name}.player_classrooms.class_id from {db_name}.player_classrooms
                                           WHERE {db_name}.player_classrooms.player_id=%s"""
                        query_params = (player_id,)
                        results = SQL.Query(cursor=db_conn.cursor(), query=query_string, params=query_params, fetch_results=True)
                    except MySQLError as err:
                        ret_val['msg'] = "FAIL: Could not retrieve the student classrooms"
                        ret_val['status'] = "ERR_DB"
                    else:
                        # Step 3: process and return player_data
                        if results != [] and results is not None:
                            ret_val['val'] = [result[0] for result in results]
                            ret_val['msg'] = f"SUCCESS: Retrieved classrooms for {player_id}"
                        else:
                            ret_val['msg'] = f"FAIL: Could not find {player_id}"
                            ret_val['status'] = "ERR_REQ"
                    finally:
                        SQL.disconnectMySQL(db_conn)
                else:
                    ret_val['msg'] = f"FAIL: Teacher does not have access to {player_id}."
                    ret_val['status'] = "ERR_REQ"
            else:
                ret_val['msg'] = f"FAIL: Could not retrieve player classrooms, teacher is not logged in"
                ret_val['status'] = "ERR_REQ"
            return ret_val

    class ClassroomAssignStudent(Resource):
        def post(self):
            ret_val : Dict[str,Any] = {
                "val":None,
                "msg":"",
                "status":"SUCCESS",
            }
            # Step 1: get args and set up database.
            parser = reqparse.RequestParser()
            parser.add_argument("class_id")
            parser.add_argument("player_id")            
            args = parser.parse_args()
            player_id = args["player_id"]
            
            # If teacher has authenticated
            if "teacher_id" in session:
                teacher_id =  session['teacher_id']
                fd_config = settings["DB_CONFIG"]["fd_users"]
                _dummy, db_conn = SQL.ConnectDB(db_settings=fd_config)
                # Step 2: If teacher has student, then we can retrieve their name.
                if      (db_conn is not None) \
                    and      ClassroomAPI.Teacher._hasStudent(  db_conn=db_conn, db_name=fd_config["DB_NAME"], teacher_id=teacher_id, student_id=player_id) \
                    and (not ClassroomAPI.Student._hasClassroom(db_conn=db_conn, db_name=fd_config["DB_NAME"], student_id=player_id,          class_id=args["class_id"])):
                    try:
                        db_name = fd_config['DB_NAME']
                        query_string = f"""INSERT INTO {db_name}.player_classrooms
                                           (`player_id`, `class_id`)
                                           VALUES (%s, %s)"""
                        query_params = (player_id, args["class_id"])
                        SQL.Query(cursor=db_conn.cursor(), query=query_string, params=query_params, fetch_results=False)
                    except MySQLError as err:
                        ret_val['msg'] = "FAIL: Could not add student to classroom"
                        ret_val['status'] = "ERR_DB"
                    else:
                        # Step 3: process and return player_data
                        ret_val['msg'] = f"SUCCESS: Added {player_id} to classroom"
                    finally:
                        SQL.disconnectMySQL(db_conn)
                else:
                    ret_val['msg'] = f"FAIL: Teacher does not have access to {player_id}."
                    ret_val['status'] = "ERR_REQ"
            else:
                ret_val['msg'] = f"FAIL: Could not add student to classroom, teacher is not logged in"
                ret_val['status'] = "ERR_REQ"
            return ret_val
