import Leap
from Xlib import X, XK
from Xlib.display import Display
from Xlib.ext.xtest import fake_input
from gi.repository import Gdk, Gtk, GObject
import sys, time
from Leap import CircleGesture, ScreenTapGesture, SwipeGesture

class MouseWrapper(object):

    MOVE_FACTOR = 8.0
    MOVE_THRESHOLD = 150.0
    ACTIVITIES_KEY = XK.XK_Super_L
    CHANGING_APPS_BASE_KEY = XK.XK_Meta_L
    CHANGING_APPS_KEY = XK.XK_Tab
    CHANGING_APPS_TIMEOUT = 1500

    def __init__(self):
        self._display = Display()
        self._device = self._get_mouse_device()
        self._screen = Gdk.Screen.get_default()
        self._run_times = {}
        self._last_move = 0
        self._changing_app_timeout_id = 0
        self._last_change_app_time = 0
        self._glib_context = None

    def _get_mouse_device(self):
        display = Gdk.Display.get_default()
        manager = display.get_device_manager()
        for device in manager.list_devices(Gdk.DeviceType.MASTER):
            if device.get_source() == Gdk.InputSource.MOUSE:
                return device
        return None

    def set_pointer(self, x, y):
        screen, pos_x, pos_y = self._device.get_position()
        current_time = time.time()
        if current_time - self._last_move > .5:
            if abs(pos_x - x) > self.MOVE_THRESHOLD or abs(pos_y - y) > self.MOVE_THRESHOLD:
                self._device.warp(screen, x, y)
                self._last_move = current_time
        else:
            self._device.warp(screen, x, y)
            if abs(pos_x - x) > 2.0:
                self._last_move = current_time

    def click(self):
        fake_input(self._display, X.ButtonPress, 1)
        fake_input(self._display, X.ButtonRelease, 1)
        self._display.sync()

    def toggle_activities(self):
        self._run_function(self._toggle_activities_real, .5)

    def _toggle_activities_real(self):
        key = self._display.keysym_to_keycode(self.ACTIVITIES_KEY)
        fake_input(self._display, X.KeyPress, key)
        fake_input(self._display, X.KeyRelease, key)
        self._display.sync()

    def _run_function(self, function, timeout, *args):
        last_run = self._run_times.get(function, 0)
        current_time = time.time()
        if current_time - last_run > timeout:
            function(*args)
        self._run_times[function] = current_time

    def next_app(self):
        print '???', self._changing_app_timeout_id
        current_time = time.time()
        if current_time - self._last_change_app_time < .5:
            return
        if self._changing_app_timeout_id == 0:
            key = self._display.keysym_to_keycode(self.CHANGING_APPS_BASE_KEY)
            fake_input(self._display, X.KeyPress, key)
        else:
            GObject.source_remove(self._changing_app_timeout_id)
            self._changing_app_timeout_id = 0
        key = self._display.keysym_to_keycode(self.CHANGING_APPS_KEY)
        fake_input(self._display, X.KeyPress, key)
        fake_input(self._display, X.KeyRelease, key)
        self._display.sync()
        self._changing_app_timeout_id = GObject.timeout_add(self.CHANGING_APPS_TIMEOUT,
                                                            self._stop_changing_apps)
        self._last_change_app_time = current_time

    def _stop_changing_apps(self, data):
        print 'STOP'
        key = self._display.keysym_to_keycode(self.CHANGING_APPS_BASE_KEY)
        fake_input(self._display, X.KeyRelease, key)
        self._display.sync()
        self._changing_app_timeout_id = 0
        return False

    def timeout_add(self, context, timeout, priority, callback, data):
        if not self._glib_context:
            self._glib_context = GObject.MainContext().get_threaded_default()
        

class ControllerListener(Leap.Listener):

    MIN_CIRCLE_RADIUS = 100.0
    MIN_SWIPE_LENGTH = 150.0
    ENABLED_GESTURES = [Leap.Gesture.TYPE_CIRCLE,
                        Leap.Gesture.TYPE_SCREEN_TAP,
                        Leap.Gesture.TYPE_KEY_TAP,
                        Leap.Gesture.TYPE_SWIPE]

    def on_init(self, controller):
        screen = Gdk.Screen.get_default()
        self._mouse_wrapper = MouseWrapper()
        self._screen_width = screen.get_width()
        self._screen_height = screen.get_height()

    def on_connect(self, controller):
        #print 'SAVE', controller.config.set('Gesture.Swipe.MinLength', self.MIN_SWIPE_LENGTH), controller.config.set('Gesture.Circle.MinRadius', self.MIN_CIRCLE_RADIUS), controller.config.set('Gesture.Circle.MinArc', 2 * Leap.PI)
        if controller.config.set('Gesture.Circle.MinArc', 2 * Leap.PI) and \
           controller.config.set('Gesture.Circle.MinRadius', self.MIN_CIRCLE_RADIUS) and \
           controller.config.set('Gesture.Swipe.MinLength', self.MIN_SWIPE_LENGTH):
            controller.config.save()

        for gesture in self.ENABLED_GESTURES:
            controller.enable_gesture(gesture)

    def on_frame(self, controller):
        frame = controller.frame()

        if frame.hands.empty:
            return

        swipe_gestures = []
        if len(frame.fingers) < 3:
            for gesture in frame.gestures():
                if gesture.type == Leap.Gesture.TYPE_KEY_TAP:
                    screentap = ScreenTapGesture(gesture)
                    self._mouse_wrapper.click()
                    return

                if gesture.type == Leap.Gesture.TYPE_CIRCLE:
                    print 'Toggle activities'
                    self._mouse_wrapper.toggle_activities()

            interaction_box = frame.interaction_box
            if frame.pointables:
                pointable = frame.pointables.frontmost
                normalized_position = interaction_box.normalize_point(pointable.tip_position)
                self._mouse_wrapper.set_pointer(normalized_position.x * self._screen_width,
                                                self._screen_height - normalized_position.y * self._screen_height)


        if len(frame.fingers) > 4:
            for gesture in frame.gestures():
                if gesture.type == Leap.Gesture.TYPE_SWIPE:
                    swipe = SwipeGesture(gesture)
                    #print 'Change app', frame, swipe, len(frame.gestures())
                    if not swipe_gestures:
                        swipe_gestures.append(swipe)
                        continue
                    previous_swipe_gesture = swipe_gestures[0]
                    #print 'SWIPE', len(swipe_gestures)
                    if abs(previous_swipe_gesture.direction.roll - swipe.direction.roll) < Leap.PI / 2.0:
                        swipe_gestures.append(swipe)
                    if len(swipe_gestures) > 2:
                        self._mouse_wrapper.next_app()

def main():
    listener = ControllerListener()
    controller = Leap.Controller()

    controller.add_listener(listener)
    sys.stdin.readline()
    controller.remove_listener(listener)

if __name__ == "__main__":
    main()
