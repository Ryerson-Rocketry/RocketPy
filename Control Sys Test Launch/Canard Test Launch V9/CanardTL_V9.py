from rocketpy import Environment, Rocket, Flight, GenericMotor, TrapezoidalFin, Function
import pandas as pd
import numpy as np
from math import pi

#ORGANIZING WEATHER DATA
weather_data = pd.read_csv("wind_2026-11-03T17.csv")
alt = weather_data["altitude"].values
speed = weather_data["speed"].values
direction = weather_data["direction"].values

direction_rad = np.radians(direction)

wind_u = -speed * np.sin(direction_rad)
wind_v = -speed * np.cos(direction_rad)

wind_u_func = Function(np.column_stack((alt, wind_u)))
wind_v_func = Function(np.column_stack((alt, wind_v)))

#ORGANIZING GENERAL DRAG DATA
drag_data = pd.read_csv(
    "canard_drag_curve.csv",
    comment = "#",
    header = None,
    names = ["cd", "mach"],
)

neworder = ['mach', 'cd']
drag_data = drag_data.reindex(columns = neworder)

drag_data.to_csv(
    "drag_curve_clean_flipped.csv",
    index = False,
    header = False,
)

#ORGANIZING POWER OFF DRAG DATA
drag_data_off = pd.read_csv(
    "canard_power_off_drag.csv",
    comment = "#",
    header = None,
    names = ["mach", "cd"],
)

drag_data_off = drag_data_off.sort_values("mach")

drag_data_off.to_csv(
    "drag_curve_power_off.csv",
    index = False,
    header = False,
)

#ORGANIZING POWER ON DRAG DATA
drag_data_on = pd.read_csv(
    "canard_power_on_drag.csv",
    comment = "#",
    header = None,
    names = ["mach", "cd"],
)

drag_data_on = drag_data_on.sort_values("mach")

drag_data_on.to_csv(
    "drag_curve_power_on.csv",
    index = False,
    header = False,
)

# SETTING ROCKET VARIABLES 
env = Environment(
    latitude= 28.61,
    longitude= -80.6,
    elevation= 0,
)

env.set_atmospheric_model(
    type = "custom_atmosphere",
    wind_u = wind_u_func,
    wind_v = wind_v_func,
)

CanardTL = Rocket(
    radius= 0.102/2,
    mass= 6.546,
    inertia= (2.152, 2.152, 0.015),
    power_off_drag= "drag_curve_power_off.csv",
    power_on_drag= "drag_curve_power_on.csv",
    center_of_mass_without_motor= 0.972,
    coordinate_system_orientation= "nose_to_tail",
)

noseset = CanardTL.add_nose(
    length= 0.406,
    kind= "ogive",
    position= 0,
)

tailset = CanardTL.add_tail(
    top_radius= 0.127/2.0,
    bottom_radius= 0.102/2.0,
    length= 0.0635,
    position= 1.8565,
)

invertedtailset = CanardTL.add_tail(
    top_radius= 0.102/2.0,
    bottom_radius= 0.127/2.0,
    length=0.102,
    position= 1.5208,
)

finset = CanardTL.add_trapezoidal_fins(
    n= 4,
    root_chord= 0.229,
    tip_chord= 0.0889,
    span= 0.102,
    cant_angle= 0,
    sweep_length= 0.185,
    radius= 0.127/2.0,
    position= 1.63,
)

canard1 = TrapezoidalFin(
    angular_position= 0,
    root_chord= 0.0254,
    tip_chord= 0,
    span= 0.03,
    rocket_radius= 0.102/2,
    cant_angle= 0,
)

canard2 = TrapezoidalFin(
    angular_position= 180,
    root_chord= 0.0254,
    tip_chord= 0,
    span= 0.03,
    rocket_radius= 0.102/2,
    cant_angle= 0,
)

CanardTL.add_surfaces([canard1, canard2], positions= 0.483)

motor = GenericMotor.load_from_eng_file("Cesaroni_2856L910-P.eng")

motorset = CanardTL.add_motor(
    motor= motor,
    position= 1.92,
)

cd = 0.8
RadiusDrogue = 0.635/2.0
RadiusMain = 1.83/2.0

ParachuteMset = CanardTL.add_parachute(
    name= "Main",
    cd_s= cd*pi*RadiusMain**2,
    trigger= 457,
    sampling_rate= 100,
    lag= 0,
)

ParachuteDset = CanardTL.add_parachute(
    name= "Drogue",
    cd_s= cd*pi*RadiusDrogue**2,
    trigger= 'apogee',
    sampling_rate= 100,
    lag= 0,
)

#CanardTL.draw(plane="yz")

test_flight = Flight(
    rocket= CanardTL,
    environment= env,
    rail_length= 6.1,
    inclination= 88,
    heading= 90,
)

#test_flight.all_info()


