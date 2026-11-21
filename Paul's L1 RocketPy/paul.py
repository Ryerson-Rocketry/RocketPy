import datetime

from rocketpy import Environment, Flight, Function, Rocket, SolidMotor

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

from pathlib import Path
from rocketpy.simulation import FlightDataExporter

env = Environment(
    date = (2026, 7, 11, 14),
    latitude = 42.70446,
    longitude = -77.19169,
    elevation = 421.7
)

weather_data = pd.read_csv("wind_2026-07-11T15.csv")

alt = weather_data["altitude"].values
speed = weather_data["speed"].values
direction = weather_data["direction"].values

direction_rad = np.radians(direction)

wind_u = -speed * np.sin(direction_rad) 
wind_v = -speed * np.cos(direction_rad) 

wind_u_func = Function(np.column_stack((alt, wind_u)))

wind_v_func = Function(np.column_stack((alt, wind_v)))

env.set_atmospheric_model(
    type = "custom_atmosphere",
    wind_u = wind_u_func,
    wind_v = wind_v_func,
)

env.plots.atmospheric_model()
env.info()

h550 = SolidMotor(
    thrust_source = "AeroTech_HP-H550ST.eng",
    dry_mass = 0.140,
    dry_inertia = (0.00260, 0.00260, 0.000111),
    nozzle_radius = 0.012446,
    grain_number = 3,
    grain_density = 1880,
    grain_outer_radius = 0.0332232 / 2,
    grain_initial_inner_radius = 0.0154686 / 2,
    grain_initial_height = 0.046101,
    grain_separation = 0.0015875,
    grains_center_of_mass_position = 0.11049,
    center_of_dry_mass_position = 0.10287,
    nozzle_position = 0,
    burn_time = 0.57,
    throat_radius = 0.00622040816,
    coordinate_system_orientation = "nozzle_to_combustion_chamber",
)

h550.info()
h550.draw()

Phoenix = Rocket(
    radius = 0.0508,
    mass = 1.497,
    inertia = (0.193465243, 0.193515502, 0.000334175),
    power_off_drag = "paul_data_sorted.csv",
    power_on_drag = "paul_data_sorted.csv",
    center_of_mass_without_motor = 0.52986,
    coordinate_system_orientation = "tail_to_nose",
)

Phoenix.add_motor(h550, position = 0)

nose_cone = Phoenix.add_nose(
    length=0.32385, kind="ogive", position=1.18700 
)

fin_set = Phoenix.add_trapezoidal_fins(
    n=3,
    root_chord = 0.200025 ,
    tip_chord = 0.0635,
    span = 0.1063752,
    position = 0.20157,
    cant_angle = 0,
)

main = Phoenix.add_parachute(
    name = "Main",
    cd_s = 0.4922,
    trigger = "apogee",
    sampling_rate = 105,
    lag = 1.5,
    noise = (0, 8.3, 0.5),
    drag_coefficient = 0.75
)

rail_buttons = Phoenix.set_rail_buttons(
    upper_button_position = 0.4700016,
    lower_button_position = 0.0254,
    angular_position = 0,
)

Phoenix.draw()

urrgFlight = Flight(
    rocket=Phoenix,
    environment=env,
    max_time_step=0.001,
    rail_length=3.04800,
    inclination=86,          # Rail inclination angle (degrees from horizontal)
    heading=35,              # Launch direction (degrees from North)
)

# Get the final simulated time
landing_time = urrgFlight.solution[-1][0]

# Calculate the coordinates at that time
landing_latitude = float(urrgFlight.latitude(landing_time))
landing_longitude = float(urrgFlight.longitude(landing_time))

print(f"Landing latitude:  {landing_latitude:.7f}")
print(f"Landing longitude: {landing_longitude:.7f}")

print(f"Landing coordinates: {landing_latitude:.7f}, {landing_longitude:.7f}")

# urrgFlight.plots.all()

# Export trajectory to KML
kml_file = "Phoenix_URRG_trajectory.kml"

FlightDataExporter(urrgFlight).export_kml(
    file_name=kml_file,
    extrude=True,
    altitude_mode="relativetoground",)

# print(f"KML saved here: {Path(kml_file).resolve()}")