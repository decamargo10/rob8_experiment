import glob
import os
import threading
import tkinter as tk
from tkinter import ttk
import datetime
import data_streamer
from threading import Thread
import re
import json
import numpy as np
import matplotlib.pyplot as plt

id = 1

class EyeTrackingExperimentUI:
    def __init__(self, id, recordings_path):
        self.recordings_path = recordings_path
        self.id = id
        self.event = threading.Event()
        # create the main window
        self.window = tk.Tk()
        self.window.title("Eye tracking experiment")
        self.window.configure(background="lightgray")

        # use a theme
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # set font
        self.font = ("Roboto", 10)

        # create the left frame

        left_frame = ttk.Frame(self.window, padding=10)
        left_frame.grid(row=0, column=0, sticky="nw")

        # create the list of checkboxes for what to store
        ttk.Label(left_frame, text="Select what to store.", font=self.font).grid(row=0, column=0, sticky="w")
        self.store_all = tk.BooleanVar(value=True)
        self.store_timestamp = tk.BooleanVar()
        self.store_frame = tk.BooleanVar()
        self.store_gaze_dir = tk.BooleanVar()
        self.store_gaze_orient = tk.BooleanVar()
        self.store_all.trace_add("write", self.all_checked)
        ttk.Checkbutton(left_frame, text="All", variable=self.store_all).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(left_frame, text="Timestamp", variable=self.store_timestamp).grid(row=2,
                                                                                          column=0,
                                                                                          sticky="w")
        ttk.Checkbutton(left_frame, text="Frame", variable=self.store_frame).grid(row=3, column=0,
                                                                                  sticky="w")
        ttk.Checkbutton(left_frame, text="Gaze dir", variable=self.store_gaze_dir).grid(row=4, column=0,
                                                                                        sticky="w")
        ttk.Checkbutton(left_frame, text="Gaze orient", variable=self.store_gaze_orient).grid(row=5,
                                                                                              column=0,
                                                                                              sticky="w")

        # create the right frame
        right_frame = ttk.Frame(self.window, padding=10)
        right_frame.grid(row=0, column=1, sticky="ne")

        # create the list of checkboxes for object of interest
        ttk.Label(right_frame, text="Object of interest", font=self.font).grid(row=0, column=0, sticky="w")
        self.object_of_interest = tk.StringVar()
        objects = ["Tool", "Beer", "Bolt", "Screwdriver"]
        self.object_of_interest.set(objects[0])
        self.create_objects_of_interest(objects, right_frame, self.object_of_interest, 2, "w")
        ttk.Separator(self.window, orient="horizontal").grid(row=1, column=0, columnspan=2, sticky="ew", padx=10,
                                                             pady=10)

        # create the bottom frame
        bottom_frame = ttk.Frame(self.window, padding=10)
        bottom_frame.grid(row=2, column=0, columnspan=2, sticky="s")

        # create the start/stop button
        self.is_running = False
        self.start_stop_button = ttk.Button(bottom_frame, text="Start", command=self.start_stop_clicked)
        self.start_stop_button.grid(row=0, column=0, pady=10)
        # mark last recording as incomplete
        self.mark_as_incomplete_button = ttk.Button(bottom_frame, text="Mark last recording as incomplete", command=self.mark_as_incomplete_clicked)
        self.mark_as_incomplete_button.grid(row=1, column=0, pady=10)
        # Create elapsed time label
        self.elapsed_time_label = tk.ttk.Label(bottom_frame, text="00:00")
        self.elapsed_time_label.grid(row=2, column=0, pady=10)
        self.id_label = ttk.Label(bottom_frame, text="Recording ID: " + str(self.id), font=self.font)
        self.id_label.grid(row=3, column=0)

        # set the layout constraints for the main window
        self.window.columnconfigure(0, weight=1)
        self.window.columnconfigure(1, weight=1)
        self.window.rowconfigure(0, weight=1)

    def create_objects_of_interest(self, objects, frame, var, start_row, sticky):
        row = start_row
        column = 0
        for o in objects:
            self.create_new_object_of_interest(frame, o, var, row, column, sticky)
            row = row + 1



    def create_new_object_of_interest(self, frame, text, var, row, column, sticky):
        return ttk.Radiobutton(frame, text=text, variable=var, value=text).grid(row=row, column=column, sticky=sticky)

    def all_checked(self, *args):
        if self.store_all.get():
            self.store_timestamp.set(False)
            self.store_frame.set(False)
            self.store_gaze_dir.set(False)
            self.store_gaze_orient.set(False)

    def mark_as_incomplete_clicked(self):
        last_rec = sorted(glob.glob(self.recordings_path + "\\*"))[-1]
        old_name = os.path.basename(os.path.normpath(last_rec))
        new_name = "INCOMPLETE_" + old_name
        os.rename(self.recordings_path + "\\" + old_name, self.recordings_path + "\\" + new_name)

    def start_stop_clicked(self):
        self.is_running = not self.is_running
        if self.is_running:
            self.start_stop_button.configure(text="Stop", style="Danger.TButton")
            selected_what_to_store = []
            if self.store_all.get():
                selected_what_to_store.append("All")
            else:
                if self.store_timestamp.get():
                    selected_what_to_store.append("Timestamp")
                if self.store_frame.get():
                    selected_what_to_store.append("Frame")
                if self.store_gaze_dir.get():
                    selected_what_to_store.append("Gaze Direction")
                if self.store_gaze_orient.get():
                    selected_what_to_store.append("Gaze Orientation")
            self.to_store = selected_what_to_store
            print("Recording started. Saving: " + str(
                selected_what_to_store) + " | Object: " + self.object_of_interest.get())
            self.rec_dir = self.recordings_path + "\\rec_id" + "{:05d}".format(self.id)
            os.mkdir(self.rec_dir)
            self.start_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.start_time = datetime.datetime.now()
            self.update_elapsed_time()
            self.create_meta_file(self.rec_dir, self.id, self.to_store, self.object_of_interest.get(),
                                  self.start_timestamp, "0:00:00")
            print("Started")
            self.event.clear()
            streamerThread = data_streamer.StreamerThread(id=self.id, recording_path=self.rec_dir)
            thread = Thread(target=streamerThread.threaded_function, args=(self.event, 20))
            thread.start()
        else:
            self.event.set()
            self.start_stop_button.configure(text="Start", style="TButton")
            self.elapsed_time = datetime.datetime.now() - self.start_time
            elapsed_time_str = str(self.elapsed_time).split(".")[0]
            self.elapsed_time_label.config(text=elapsed_time_str)
            self.create_meta_file(self.rec_dir, self.id, self.to_store, self.object_of_interest.get(), self.start_timestamp, elapsed_time_str)
            print("Recording stopped. Recorded time: " , elapsed_time_str)
            self.id = self.id + 1
            self.id_label.configure(text="Recording ID: " + str(self.id))

    def update_elapsed_time(self):
        if self.is_running:
            elapsed_time = datetime.datetime.now() - self.start_time
            elapsed_time_str = str(elapsed_time).split(".")[0]  # remove microseconds
            self.elapsed_time_label.configure(text=elapsed_time_str)
            self.window.after(1000, self.update_elapsed_time)


    def create_meta_file(self, save_dir, id, stored_types, object_of_interest, timestamp_start, duration):
        data = {
            "id": id,
            "stored_types": stored_types,
            "object_of_interest": object_of_interest,
            "timestamp": timestamp_start,
            "recording_duration": duration
        }

        with open(save_dir + "\\meta.json", "w") as f:
            json.dump(data, f, indent=4)



def main():
    recordings_path = os.getcwd() + "\\recordings"
    recs = sorted(glob.glob(recordings_path + "\\*", recursive=False))
    if len(recs) > 0:
        match = re.search(r'(\d+)$', recs[-1]).group()
        id = int(match) + 1
    else:
        id = 0
    ui = EyeTrackingExperimentUI(id, recordings_path)
    ui.window.mainloop()

if __name__ == "__main__":
    main()

