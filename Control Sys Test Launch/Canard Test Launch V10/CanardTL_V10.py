from rocketpy import Environment, Rocket, Flight, SolidMotor, TrapezoidalFin, Function
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


#---------------------------------------- ORGANIZING POWER OFF DRAG DATA -----------------------------------------------------------
drag_data_off = pd.read_csv(
    "power_off_curve_raw.csv",
    comment = "#",
    header = None,
    names = ["cd", "mach"],
)

neworder = ['mach', 'cd']
drag_data_off = drag_data_off.reindex(columns = neworder)

drag_data_off.to_csv(
    "power_off_curve_flipped.csv",
    index = False,
    header = False,
)

drag_data_off = pd.read_csv(
    "power_off_curve_flipped.csv",
    comment = "#",
    header = None,
    names = ["mach", "cd"],
)

drag_data_off = drag_data_off.sort_values("mach")

drag_data_off.to_csv(
    "power_off_drag_curve_clean.csv",
    index = False,
    header = False,
)

#----------------------------------------------- ORGANIZING POWER ON DRAG DATA -------------------------------------------
drag_data_on = pd.read_csv(
    "power_on_curve_raw.csv",
    comment = "#",
    header = None,
    names = ["cd", "mach"],
)

neworder = ['mach', 'cd']
drag_data_on = drag_data_on.reindex(columns = neworder)

drag_data_on.to_csv(
    "power_on_curve_flipped.csv",
    index = False,
    header = False,
)

drag_data_on = pd.read_csv(
    "power_on_curve_flipped.csv",
    comment = "#",
    header = None,
    names = ["mach", "cd"],
)

drag_data_on = drag_data_on.sort_values("mach")

drag_data_on.to_csv(
    "power_on_drag_curve_clean.csv",
    index = False,
    header = False,
)

# --------------------------------------------------- SETTING ROCKET VARIABLES --------------------------------------------------- 
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
    mass= 6.918,
    inertia= (2.391, 2.391, 0.015),
    power_off_drag= "power_off_drag_curve_clean.csv",
    power_on_drag= "power_on_drag_curve_clean.csv",
    center_of_mass_without_motor= 0.981,
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
    length= 0.064,
    position= 1.856,
)

invertedtailset = CanardTL.add_tail(
    top_radius= 0.102/2.0,
    bottom_radius= 0.127/2.0,
    length=0.102,
    position= 1.525,
)

finset = CanardTL.add_trapezoidal_fins(
    n= 4,
    root_chord= 0.229,
    tip_chord= 0.0889,
    span= 0.102,
    cant_angle= 0,
    sweep_length= 0.185,
    radius= 0.127/2.0,
    position= 1.626,
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

railbuttonset = CanardTL.set_rail_buttons(
    lower_button_position=1.22-0.0582,
    upper_button_position=1.22,
)

CanardTL.add_surfaces([canard1, canard2], positions= 0.483)

L910 = SolidMotor(
    thrust_source= ("Cesaroni_2856L910-P.eng"),
    nozzle_position= 0,
    coordinate_system_orientation= "nozzle_to_combustion_chamber",

    dry_mass= 1.05444741,
    center_of_dry_mass_position= 0.16659244,
    dry_inertia = (0.01791230, 0.01791230, 0.00112808),

    nozzle_radius= 0.04699/2.0,
    throat_radius= 0.02159/2.9,

    grain_number= 2,
    grain_density= 1669.286,
    grain_outer_radius= 0.0643/2.0,
    grain_initial_inner_radius= 0.01905/2.0,
    grain_initial_height= 0.1356,
    grain_separation= 0.0025,
    grains_center_of_mass_position= 0.20940113,
)

motorset = CanardTL.add_motor(
    motor= L910,
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

CanardTL.draw(plane="yz")

test_flight = Flight(
    rocket= CanardTL,
    environment= env,
    rail_length= 6.1,
    inclination= 88,
    heading= 90,
)

#test_flight.all_info()
#test_flight.stability_margin()
#L910.all_info()

print("Rocket CM:", CanardTL.center_of_mass(0), "m")
print("Rocket CP:", CanardTL.cp_position(0), "m")
#CanardTL.all_info()


