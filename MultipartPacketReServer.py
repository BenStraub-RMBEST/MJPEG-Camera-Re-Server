import requests
import threading
from flask import Flask, Response
from typing import Callable

class MultipartPacketReServer:
    def __init__(self, input_url : str, flaskapp : Flask, url_route : str, cam_name : str, print_func : Callable[str,None] = print):
        self._input_url = input_url
        self.cam_name = cam_name
        self.url_route = url_route
        self.NUM_BUFFERS = 4
        self._bufs = [None]*self.NUM_BUFFERS
        self._headidx = 0
        self._print = print_func
        
        # stop event for flagging to kill the packet server
        self.stop_event = threading.Event()
        
        # condtion for flagging to waiting clients when a new frame is available
        self._new_frame_condition = threading.Condition()
        # setup and start input stream thread
        self._rx_thread = threading.Thread(target=self._connect_and_process_input)
        #self._rx_thread.daemon = True
        self._rx_thread.start()
        # start server for output streams
        flaskapp.add_url_rule('/'+url_route, url_route, view_func=self.video_client)
        
    def _connect_and_process_input(self):
        while not self.stop_event.is_set():
            try:
                req = requests.get(self._input_url, stream=True, timeout=1)
                if req.status_code != 200:
                    self._print('ERROR: ' + self.cam_name + ': request to input "'+self._input_url+'" ('+self.url_route+') failed with status '+str(req.status_code))
                    return
                
                if len(req.headers['content-type']) < 26 or req.headers['content-type'][0:26] != 'multipart/x-mixed-replace;':
                    self._print('ERROR: ' + self.cam_name + ': unexpected content-type on '+self.url_route+', are you sure this is an ESP32 camera?' + 
                          ' Expected "multipart/x-mixed-replace;boundary=...", got "'+req.headers['content-type']+'"')
                    return
                
                bound_split = req.headers['content-type'][26:].split('=',1)
                if len(bound_split) != 2 or bound_split[0] != 'boundary':
                    self._print('ERROR: ' + self.cam_name + ': could not find boundary for multipart content.')
                    return
                self._boundary = bound_split[1]
                self._bound_w_dash_enc = b'--' + self._boundary.encode()
                
                #pkt_cnt = 0
                for line in req.iter_lines(chunk_size=256*1024, delimiter=self._bound_w_dash_enc):
                    self._bufs[self._headidx] = line
                    self._headidx = (self._headidx + 1) % self.NUM_BUFFERS
                    with self._new_frame_condition: # acquire lock
                        self._new_frame_condition.notify_all() # notify any waiting threads that the next frame is ready
                    #pkt_cnt += 1
                    if self.stop_event.is_set():
                        break
                    #print(str(pkt_cnt))
                self._print('WARNING: ' + self.cam_name + ': Camera feed input stream ended on ' + self.url_route + ', attempting reconnect.')
            except requests.exceptions.Timeout:
                self._print('WARNING: ' + self.cam_name + ': Camera feed input timeout on ' + self.url_route + ', retrying.')
            except requests.exceptions.ConnectionError:
                self._print('WARNING: ' + self.cam_name + ': Camera feed input connection error on ' + self.url_route + ', retrying.')
                # TODO: insert error frame perhaps?
            except requests.exceptions.RequestException as e:
                self._print('ERROR: ' + self.cam_name + ': Camera input on '+self.url_route+' failed with request exception: ' + str(e))
                return
            
    def _frame_generator(self):
        #alpha=['a', 'b', 'c', 'd']
        last_idx_served = -1
        while True:
            #print('_')
            idx = (self._headidx - 1) % self.NUM_BUFFERS
            if idx == last_idx_served:
                #print('WfL')
                with self._new_frame_condition: # acquire lock
                    #print('Acq')
                    # one more check to make sure the idx didn't change while acquiring lock...
                    # I could just lock everytime, but I worry that multiple consumer threads might
                    # fight for lock in that case and hurt framerate, so better to only lock when it
                    # really seems like you need to.
                    if idx == (self._headidx - 1) % self.NUM_BUFFERS:
                        #print('WfC')
                        # wait until notified that new frame is ready
                        self._new_frame_condition.wait() # TODO: consider setting a timeout to resend a duplicate frame to keep connection alive???
                    #else: # else idx changed while locking, so just unlock and carry-on (go back to beginning of loop to get new idx)
                    #    print('Rel')
                #continue
            else:
                last_idx_served = idx
                #print(alpha[idx])
                yield self._bound_w_dash_enc + self._bufs[idx]
        # while loop
        
    def video_client(self):
        #return "TESTING THE WEB PAGE!"
        return Response(self._frame_generator(), mimetype='multipart/x-mixed-replace;boundary='+self._boundary, headers={'Connection':'keep-alive'})
        
    def stop(self):
        self.stop_event.set()
        
    def stop_and_join(self):
        self.stop_event.set()
        self._rx_thread.join()
        
    def join(self):
        self._rx_thread.join()
        
if __name__ == "__main__":
    app = Flask(__name__)
    
    test_inst = MultipartPacketReServer('http://192.168.10.11', app, 'red1', 'red1')
    print('About to start webserver!')
    #app.add_url_rule('/video', 'video', view_func=test_inst.video_client)
    app.run(host='0.0.0.0', port=8357)
    
    # TODO: catch keyboard interrupt