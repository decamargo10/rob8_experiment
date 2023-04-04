"""This file handles the data streaming and storing loop"""
import threading
from time import sleep
from pynput import keyboard
import numpy as np
import multiprocessing as mp
import cv2
import hl2ss_imshow
import hl2ss
import hl2ss_mp
import queue
import json

# Params --------------------------------------------------------------------

# HoloLens address
from experiment import hl2ss_3dcv

host = '192.168.1.22'

# Ports
ports = [
    hl2ss.StreamPort.PERSONAL_VIDEO
]
draw_fixation_points = True
# PV parameters
pv_mode = hl2ss.StreamMode.MODE_1
pv_width = 1504
pv_height = 846
pv_framerate = 30
pv_profile = hl2ss.VideoProfile.H265_MAIN
pv_bitrate = 5 * 1024 * 1024
pv_format = 'bgr24'

# Maximum number of frames in buffer
buffer_elements = 240


# END Params ----------------------------------------------------------------

class StreamerThread():
    def __init__(self, id, recording_path):
        self.recording_path = recording_path
        self.result = cv2.VideoWriter(recording_path + '\\recording' + str(id) + '.mp4',
                                 fourcc=cv2.VideoWriter_fourcc(*'mpv4'),
                                 fps=pv_framerate, frameSize=(pv_width, pv_height))
        self.id = id
        self.frames_queue = queue.Queue()
        self.save_thread_event = threading.Event()
        self.finished_writing_video = False
        self.last_image = np.zeros((pv_height, pv_width, 3))
        self.fixation_points = []
        self.last_ixy = (0,0)
        self.ixy_counter = 0
        self.frame_index = 0

    def threaded_function(self, event, arg):
        thread = threading.Thread(target=self.save_frames)
        thread.start()
        client_rc = hl2ss.ipc_rc(host, hl2ss.IPCPort.REMOTE_CONFIGURATION)
        hl2ss.start_subsystem_pv(host, hl2ss.StreamPort.PERSONAL_VIDEO)
        self.calibration = hl2ss.download_calibration_pv(host, hl2ss.StreamPort.PERSONAL_VIDEO, pv_width, pv_height,
                                                         pv_framerate)
        client_rc.wait_for_pv_subsystem(True)

        producer = hl2ss_mp.producer()
        producer.configure_si(host, hl2ss.StreamPort.SPATIAL_INPUT, hl2ss.ChunkSize.SPATIAL_INPUT)
        producer.initialize(hl2ss.StreamPort.SPATIAL_INPUT, hl2ss.Parameters_SI.SAMPLE_RATE * 5)
        producer.start(hl2ss.StreamPort.SPATIAL_INPUT)
        manager = mp.Manager()
        consumer = hl2ss_mp.consumer()
        producer.configure_pv(True, host, hl2ss.StreamPort.PERSONAL_VIDEO, hl2ss.ChunkSize.PERSONAL_VIDEO, pv_mode,
                              pv_width, pv_height, pv_framerate, pv_profile, pv_bitrate, pv_format)
        producer.initialize(ports[0], buffer_elements)
        producer.start(ports[0])

        sink_si = consumer.create_sink(producer, hl2ss.StreamPort.SPATIAL_INPUT, manager, None)
        sink_si.get_attach_response()
        sink_pv = consumer.create_sink(producer, ports[0], manager, None)
        sink_pv.get_attach_response()

        #client_pv = hl2ss.rx_decoded_pv(host, hl2ss.StreamPort.PERSONAL_VIDEO, hl2ss.ChunkSize.PERSONAL_VIDEO,
         #                               hl2ss.StreamMode.MODE_1, pv_width, pv_height, pv_framerate, pv_profile, pv_bitrate,
         #                               'bgr24')
        #client_pv.open()

        while True:
            if event.is_set():
                print("Stopping thread.")
                break
            data_pv = sink_pv.get_most_recent_frame()
            if data_pv is not None:
                if self.last_image is None or not np.array_equal(data_pv.payload.image, self.last_image):
                    data_si = sink_si.get_nearest(data_pv.timestamp)[1]
                    ixy = self.display_pv(data_pv, data_si)
                    self.last_image = data_pv.payload.image
                if self.last_ixy == ixy:
                    self.ixy_counter = self.ixy_counter + 1
                    print("Same ixy in a row: ", self.ixy_counter)
                else:
                    self.ixy_counter = 0
                if self.ixy_counter > 100:
                    print("Data stream not changing. Lost connection?")
                    # IF DATASET DOES NOT HAVE ELAPSED TIME IN META INFORMATION -> INCOMPLETE
                    break
                self.last_ixy = ixy
                cv2.waitKey(1)

        #client_pv.close()
        cv2.destroyAllWindows()
        self.save_thread_event.set()
        while not self.finished_writing_video:
            pass
        self.result.release()
        with open(self.recording_path + '\\fixation_points.json', 'w') as f:
            json.dump(self.fixation_points, f)
        sink_si.detach()
        sink_pv.detach()
        producer.stop(hl2ss.StreamPort.SPATIAL_INPUT)
        producer.stop(ports[0])
        hl2ss.stop_subsystem_pv(host, hl2ss.StreamPort.PERSONAL_VIDEO)
        client_rc.wait_for_pv_subsystem(False)
        print("Thread closed.")


    def display_pv(self, data_pv, data_si):
        #self.result.write(payload.image)
        #projection = hl2ss_3dcv.projection(self.calibration.intrinsics, hl2ss_3dcv.world_to_reference(data_pv.pose))
        si = hl2ss.unpack_si(data_si.payload)
        K = np.array([[data_pv.payload.focal_length[0], 0, data_pv.payload.principal_point[0]],
                      [0, data_pv.payload.focal_length[1], data_pv.payload.principal_point[1]],
                      [0, 0, 1]])
        eye_ray = si.get_eye_ray()
        eye_ray.origin
        eye = eye_ray.direction
        pose = (data_pv.pose)
        rvec, _ = cv2.Rodrigues(pose[:3, :3])
        tvec = pose[:3, 3]
        xy, _ = cv2.projectPoints(eye, rvec, tvec, K, None)
        ixy = (int(xy[0][0][0]), int(xy[0][0][1]))
        fp = {"eye_gaze_timestep": data_si.timestamp, "eye_gaze_point:": ixy, "corresponding_frame_timestamp": data_pv.timestamp, "video_frame_index": self.frame_index}
        self.frame_index +=1
        self.fixation_points.append(fp)
        self.save_frame(data_pv.payload.image)
        if draw_fixation_points:
            # For some reason, the circle is also drawn on the frames to be saved -> disable for recordings.
            ixy = (pv_width - ixy[0], ixy[1])
            print(ixy)
            image = data_pv.payload.image.copy()
            image = cv2.circle(image, ixy, radius=10, color=(0, 0, 255), thickness=-1)
            cv2.imshow("RecordingID: " + str(self.id), image)
        else:
            cv2.imshow("RecordingID: " + str(self.id), data_pv.payload.image)
        return ixy


    def save_frames(self):
        while not self.save_thread_event.is_set():
            try:
                frame = self.frames_queue.get(timeout=1)
            except queue.Empty:
                continue
            if self.last_image is None or not np.array_equal(frame, self.last_image):
                self.result.write(frame)
                self.last_image = frame
        while True:
            try:
                frame = self.frames_queue.get(timeout=1)
            except queue.Empty:
                break
            self.result.write(frame)
        self.finished_writing_video = True



    def save_frame(self, frame):
        # add frame to queue
        self.frames_queue.put(frame)



