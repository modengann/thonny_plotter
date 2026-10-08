"""
stop_button.py  -  an optional physical STOP button on the Raspberry Pi.

Wire a push button between a GPIO pin and ground, and put the pin's BCM
number in plotter_config.json as "stop_pin".  Pressing it does exactly what
the dashboard's STOP button does.  Off when there is no stop_pin, no
gpiozero, or no GPIO (e.g. on the laptop).
"""


def attach(pin, on_press, button_class=None):
    """Call on_press (from gpiozero's own thread) when the button is
    pressed.  Returns the button, or None if there isn't one."""
    if pin is None:
        return None
    if button_class is None:
        try:
            from gpiozero import Button as button_class
        except ImportError:
            return None
    try:
        button = button_class(pin, pull_up=True, bounce_time=0.05)
    except Exception:            # gpiozero: no GPIO on this machine
        return None
    button.when_pressed = on_press
    return button
