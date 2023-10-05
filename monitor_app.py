from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, leave_room
from flask_restful import Api, Resource

app = Flask(__name__)
api = Api(app)
app.config['SECRET_KEY'] = 'secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# game_rooms is a dict storing {game_room} and corresponding {client_id}
# { 
#   'aqualab' : ['clientIDxxxxxinRoomAqualab', 'clientIDyyyyyyinRoomAqualab'],
#   ...
# }
game_rooms = {}


@app.route('/')
def index():
    return render_template('index.html')

# given client session id
# remove it from game rooms
def remove_client_by_client_id(client_id):
    for game_name, clients in game_rooms.items():
        if client_id in clients:
            clients.remove(client_id)
            leave_room(game_name, client_id)
            # print(f'Client ID: {client_id} removed from Room {game_name}')

# given game room name and client session id
# join client to the corresponding game room
def add_client_by_client_id(game_name, client_id):
    if game_name not in game_rooms:
        game_rooms[game_name] = []

    if client_id not in game_rooms[game_name]:
        game_rooms[game_name].append(client_id)
        join_room(game_name, client_id)
        # print(f'Client ID: {client_id} added to Room {game_name}')

# when new client is "connect"
# add its id to default game room "aqualab"
@socketio.on('connect')
def handle_connect():
    client_id = request.sid
    # print(f'Client connected with ID: {client_id}')
    add_client_by_client_id("aqualab", client_id)

# when current client is "disconnect"
# remove its id from game rooms
@socketio.on('disconnect')
def handle_disconnect():
    client_id = request.sid
    remove_client_by_client_id(client_id)
    # print(f'Client disconnected with ID: {client_id}')

# when current client changes game selecor
# remove it from current game room and join to the new assigned room
@socketio.on('game_selector_changed')
def handle_game_selector_changed(selectedGame):
    client_id = request.sid
    remove_client_by_client_id(client_id)
    add_client_by_client_id(selectedGame, client_id)

# flask-restful api receiver
# allows data coming in through name space 'all-game'
# send data to corresponding room
class LoggerReceiver(Resource):
    def post(self):
        json_data = request.get_json()
        socketio.emit('logger_data', json_data, to=json_data.get('app_id'))
        return {'message': 'Received logger data successfully'}


api.add_resource(LoggerReceiver, '/all-game')

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)
