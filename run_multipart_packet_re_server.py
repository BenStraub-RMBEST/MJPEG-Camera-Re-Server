# run_multipart_packet_re_server

from MultipartPacketReServer import MultipartPacketReServer
from flask import Flask, Response
import yaml
import sys
import threading

yaml_file_name = 'camera_config.yaml'


def print_with_lock(msg : str):
    with print_with_lock.lock:
        print(msg)
print_with_lock.lock = threading.Lock()


with open(yaml_file_name, 'r') as yfile:
    config = yaml.safe_load(yfile)
    


app = Flask(__name__)

pkt_server_list = []


for entry in config['cameras']:
    try:
        inst = MultipartPacketReServer(entry['cam_url'], app, entry['path_end'], entry['name'], print_with_lock)
    except KeyError as e:
        print('ERROR while parsing config, missing expected fields')
        print(e)
        sys.exit(1)
        
    pkt_server_list.append(inst)
    
@app.route('/')
def index_page():
    page = '<html><head><style>.btndiv {border: 5px outset black; color: black; text-decoration: none; text-align: center;' +\
        'float: left; width: 200px; max-width: 50%; height: 200px; } @media screen and (max-width: 909px)'+\
        '{ .btndiv { width: 22%; } }</style></head><body><div style="width:100%;float:left;">'
    for idx,entry in enumerate(config['cameras']):
        page+='<a href="/'+entry['path_end']+'"><div class="btndiv" style="background-color:'+\
                entry['button_color']+';">'+entry['name']+'</div></a>'
        if idx%4 == 3:
            page += '</div><div style="width:100%;float:left;">'
            
    page += '</div></body></html>'
    return page

#app.add_url_rule('/video', 'video', view_func=test_inst.video_client)

app.run(host=config['server_host_ip'], port=config['server_host_port'])

print('Stopping packet server threads')
for pkt_server in pkt_server_list:
    pkt_server.stop()
for pkt_server in pkt_server_list:
    pkt_server.join()

print('All done!')