#!/usr/bin/env python
# -*- coding: utf-8 -*-

#  Leap Motion GNOME Controller
#  Copyright © 2013 Joaquim Rocha <me@joaquimrocha.com>
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import Leap
from Xlib import X, XK
from Xlib.display import Display
from Xlib.ext.xtest import fake_input
from gi.repository import Gdk
import sys, time, math
from Leap import CircleGesture, SwipeGesture

ACTIVITIES_KEY = (XK.XK_Super_L,)
MOVE_DESKTOP_BASE_KEY_COMBO = (XK.XK_Meta_L, XK.XK_Control_L)
INCREASE_ZOOM_COMBO = (XK.XK_Control_L, XK.XK_plus)
DECREASE_ZOOM_COMBO = (XK.XK_Control_L, XK.XK_minus)

class EventManager(object):

    POINTER_MOVE_THRESHOLD = 150.0 # px
    POINTER_MIN_MOVE = 2.0 # px
    POINTER_STOP_TIMEOUT = .5 # seconds
    ZOOM_THRESHOLD = 20 # mm
    ZOOM_FUNCTION_DURATION = .2 # seconds
    ZOOM_FUNCTION_RESET_TIMEOUT = 2 # seconds
    FUNCTIONS_DEFAULT_DURATION = .5 # seconds

    def __init__(self):
        self._display = Display()
        self._run_times = {}
        self._last_pointer_move = 0
        self._last_zoom = 0
        self._last_zoom_distance = -1

    def _set_pointer(self, x, y):
        fake_input(self._display, X.MotionNotify, x=x, y=y)
        self._display.sync()

    def move_pointer(self, x, y):
        '''
        Moves the pointer unless it remains for longer than POINTER_STOP_TIMEOUT
        without moving (more than POINTER_MIN_MOVE). In a non-movement state,
        the pointer needs to move more than POINTER_MOVE_THRESHOLD to actually
        move for real.
        '''
        data = self._display.screen().root.query_pointer()._data
        pos_x, pos_y = data['root_x'], data['root_y']
        current_time = time.time()
        if current_time - self._last_pointer_move > self.POINTER_STOP_TIMEOUT:
            dist = math.sqrt(pow(pos_x - x, 2) + pow(pos_y - y, 2))
            # Pointer is "stopped", we only move it in this condition
            if dist > self.POINTER_MOVE_THRESHOLD:
                self._set_pointer(x, y)
                self._last_pointer_move = current_time
        else:
            self._set_pointer(x, y)
            if abs(pos_x - x) > self.POINTER_MIN_MOVE:
                self._last_pointer_move = current_time

    def click(self):
        fake_input(self._display, X.ButtonPress, 1)
        fake_input(self._display, X.ButtonRelease, 1)
        self._display.sync()

    def toggle_activities(self):
        self._run_function(self._toggle_activities_real,
                           self.FUNCTIONS_DEFAULT_DURATION)

    def _toggle_activities_real(self):
        self._press_and_release_key_combo(ACTIVITIES_KEY)

    def _run_function(self, function, timeout, *args):
        '''
        Runs a function if it hasn't run for less than the
        specified timeout.
        '''
        last_run = self._run_times.get(function, 0)
        current_time = time.time()
        if current_time - last_run > timeout:
            function(*args)
        self._run_times[function] = current_time

    def _move_desktop(self, dir_keysym):
        self._press_and_release_key_combo(MOVE_DESKTOP_BASE_KEY_COMBO +
                                          (dir_keysym,))

    def move_next_desktop(self):
        self._run_function(self._move_desktop, self.FUNCTIONS_DEFAULT_DURATION,
                           XK.XK_Down)

    def move_previous_desktop(self):
        self._run_function(self._move_desktop, self.FUNCTIONS_DEFAULT_DURATION,
                           XK.XK_Up)

    def _press_and_release_key_combo(self, combo):
        for action in (X.KeyPress, X.KeyRelease):
            for keysym in combo:
                key = self._display.keysym_to_keycode(keysym)
                fake_input(self._display, action, key)
            self._display.sync()

    def _change_zoom(self, distance):
        if distance > self._last_zoom_distance:
            self._press_and_release_key_combo(INCREASE_ZOOM_COMBO)
        else:
            self._press_and_release_key_combo(DECREASE_ZOOM_COMBO)

    def zoom(self, distance):
        '''
        Uses the distance between two points to check whether the zoom
        should be increased, decreased or not applied at all.
        '''
        current_time = time.time()
        time_since_last_zoom = current_time - self._last_zoom
        if time_since_last_zoom < self.ZOOM_FUNCTION_DURATION:
            return
        if time_since_last_zoom > self.ZOOM_FUNCTION_RESET_TIMEOUT:
            self._last_zoom_distance = -1
        if self._last_zoom_distance == -1:
            self._last_zoom_distance = distance
        elif abs(self._last_zoom_distance - distance) > self.ZOOM_THRESHOLD:
            self._change_zoom(distance)
            self._last_zoom_distance = distance
        self._last_zoom = current_time

class ControllerListener(Leap.Listener):

    MIN_CIRCLE_RADIUS = 100.0
    MIN_SWIPE_LENGTH = 150.0
    ENABLED_GESTURES = [Leap.Gesture.TYPE_CIRCLE,
                        Leap.Gesture.TYPE_SCREEN_TAP,
                        Leap.Gesture.TYPE_KEY_TAP,
                        Leap.Gesture.TYPE_SWIPE]

    def __init__(self):
        Leap.Listener.__init__(self)
        screen = Gdk.Screen.get_default()
        self._event_manager = EventManager()
        self._screen_width = screen.get_width()
        self._screen_height = screen.get_height()

    def on_connect(self, controller):
        if controller.config.set('Gesture.Circle.MinArc', 2 * Leap.PI) and \
           controller.config.set('Gesture.Circle.MinRadius', self.MIN_CIRCLE_RADIUS) and \
           controller.config.set('Gesture.Swipe.MinLength', self.MIN_SWIPE_LENGTH):
            controller.config.save()

        for gesture in self.ENABLED_GESTURES:
            controller.enable_gesture(gesture)

    def handle_two_hands(self, frame):
        point1 = frame.hands.leftmost.pointables.frontmost.stabilized_tip_position
        point2 = frame.hands.rightmost.pointables.frontmost.stabilized_tip_position
        distance = point1.distance_to(point2)
        self._event_manager.zoom(distance)

    def handle_one_hand(self, frame):
        if len(frame.fingers) < 3:
            for gesture in frame.gestures():
                if gesture.type == Leap.Gesture.TYPE_KEY_TAP:
                    self._event_manager.click()
                    return

                if gesture.type == Leap.Gesture.TYPE_CIRCLE:
                    self._event_manager.toggle_activities()

            # Move the pointer
            interaction_box = frame.interaction_box
            if frame.pointables:
                pointable = frame.pointables.frontmost
                position = interaction_box.normalize_point(pointable.tip_position)
                pos_x = position.x * self._screen_width
                pos_y = self._screen_height - position.y * self._screen_height
                self._event_manager.move_pointer(pos_x, pos_y)

        if len(frame.fingers) > 4:
            swipe_gestures = []
            for gesture in frame.gestures():
                if gesture.type != Leap.Gesture.TYPE_SWIPE:
                    continue
                swipe = SwipeGesture(gesture)

                if not swipe_gestures:
                    swipe_gestures.append(swipe)
                    continue

                previous_swipe = swipe_gestures[0]
                angle_diff = previous_swipe.direction.roll - swipe.direction.roll
                if abs(angle_diff) < Leap.PI / 2.0:
                    swipe_gestures.append(swipe)

                angle = abs(swipe.direction.roll) % Leap.PI
                if len(swipe_gestures) > 2:
                    if angle < Leap.PI / 4:
                        self._event_manager.move_next_desktop()
                    if angle > Leap.PI - Leap.PI / 4:
                        self._event_manager.move_previous_desktop()

    def on_frame(self, controller):
        frame = controller.frame()

        if frame.hands.empty:
            return

        if len(frame.hands) > 1:
            self.handle_two_hands(frame)
            return

        self.handle_one_hand(frame)

def main():
    listener = ControllerListener()
    controller = Leap.Controller()

    controller.add_listener(listener)
    sys.stdin.readline()
    controller.remove_listener(listener)

if __name__ == "__main__":
    main()
