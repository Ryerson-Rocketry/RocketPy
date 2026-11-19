
# ERA5 - LATEST AVAILABLE

from rocketpy import Environment, SolidMotor, Rocket, TrapezoidalFin, Flight, Function

import numpy as np
import pandas as pd
import requests
import cdsapi

from pathlib import Path
from math import pi
from datetime import datetime, timedelta, timezone
from netCDF4 import Dataset


lat = 42.70477
long = -77.19170
elev = 268.49

env = Environment(
    date = (2026, 11, 13, 14),
    timezone = "America/New_York",
    latitude = lat,
    longitude = long,
    elevation = elev,
)

# WEATHER HERE:

folder = Path(__file__).resolve().parent

simulation_title = input("Enter simulation title: ")

safe_title = "".join(
    c if c.isalnum() or c in "-_" else "_"
    for c in simulation_title
).strip("_") or "ERA5_Simulation"


# KEEP LAUNCH TIME THE SAME
launch = "2026-11-13T19:00"

launch_dt = datetime.fromisoformat(
    launch
).replace(tzinfo=timezone.utc)

# "latest" = newest available ERA5 data
# "launch" = actual November 13 launch data

mode = "launch"


# Latest available
# Select ERA5 observation time

if mode == "launch":
    selected_dt = launch_dt

elif mode == "latest":
    selected_dt = datetime.now(timezone.utc) - timedelta(days=7)
    selected_dt = selected_dt.replace(
        hour=19, minute=0, second=0, microsecond=0
    )

else:
    raise ValueError("Mode must be 'latest' or 'launch'.")

print(f"Attempting ERA5 observation: {selected_dt}")


selected_date = selected_dt.date()

print(f"Selected ERA5 time: {selected_dt}")

if selected_dt != launch_dt:
    print(
        "WARNING: ERA5 weather is from before "
        "the actual launch."
    )


# download ERA5 weather

era5_file = folder / (
    f"ERA5_{selected_date}_19UTC.nc"
)

if not era5_file.exists():

    print("\nDownloading ERA5 weather...")

    client = cdsapi.Client()

    client.retrieve(
        "reanalysis-era5-pressure-levels",
        {
            "product_type": ["reanalysis"],

            "variable": [
                "geopotential",
                "temperature",
                "u_component_of_wind",
                "v_component_of_wind",
            ],

            "year": [
                f"{selected_date.year}"
            ],

            "month": [
                f"{selected_date.month:02d}"
            ],

            "day": [
                f"{selected_date.day:02d}"
            ],

            "time": ["19:00"],

            "pressure_level": [
                "1000", "975", "950", "925",
                "900", "875", "850", "825",
                "800", "775", "750", "700",
                "650", "600", "550", "500",
                "450", "400", "350", "300",
                "250", "200", "150", "100",
            ],

            "area": [
                43.25,
                -77.75,
                42.25,
                -76.75
            ],

            "data_format": "netcdf",
            "download_format": "unarchived",
        },
        str(era5_file)
    )

print("\nERA5 weather file saved!")
print(f"Location: {era5_file.resolve()}")
print(f"File exists: {era5_file.exists()}")


# load into rocketpy

# Use a separate environment for the ERA5
# observation so the V11 launch stays at
# November 13, 2 PM New York time

era5_env = Environment(
    date = (
        selected_date.year,
        selected_date.month,
        selected_date.day,
        19
    ),
    timezone = "UTC",
    latitude = lat,
    longitude = long,
    elevation = elev,
)


# Detect NetCDF variable names
with Dataset(str(era5_file)) as nc:

    def get_name(*names):
        for name in names:
            if name in nc.variables:
                return name

        raise KeyError(
            f"None of {names} found in ERA5 file"
        )

    era5_mapping = {
        "time": get_name("valid_time", "time"),
        "latitude": get_name("latitude", "lat"),
        "longitude": get_name("longitude", "lon"),
        "level": get_name("pressure_level", "level"),
        "temperature": get_name("t"),
        "geopotential": get_name("z"),
        "geopotential_height": None,
        "surface_geopotential_height": None,
        "u_wind": get_name("u"),
        "v_wind": get_name("v"),
    }


era5_env.set_atmospheric_model(
    type = "reanalysis",
    file = str(era5_file),
    dictionary = era5_mapping,
    pressure_conversion_factor = "hPa",
)

era5_env.set_elevation(elev)


# weather profile

max_height = min(
    float(era5_env.max_expected_height),
    15000.0
)

heights = np.arange(
    elev,
    max_height,
    100.0
)

weather = pd.DataFrame({
    "height_m_asl": heights,

    "pressure_pa": [
        float(era5_env.pressure(z))
        for z in heights
    ],

    "temperature_k": [
        float(era5_env.temperature(z))
        for z in heights
    ],

    "wind_u_mps": [
        float(era5_env.wind_velocity_x(z))
        for z in heights
    ],

    "wind_v_mps": [
        float(era5_env.wind_velocity_y(z))
        for z in heights
    ],
})


# save

weather_file = folder / (
    f"{safe_title}_ERA5_{selected_date}.csv"
)

weather.to_csv(
    weather_file,
    index=False
)

print("\nERA5 weather profile saved!")
print(f"Location: {weather_file.resolve()}")
print(f"Atmospheric levels: {len(weather)}")


# load into env

env.set_atmospheric_model(
    type = "custom_atmosphere",

    pressure = weather[
        ["height_m_asl", "pressure_pa"]
    ].to_numpy(),

    temperature = weather[
        ["height_m_asl", "temperature_k"]
    ].to_numpy(),

    wind_u = weather[
        ["height_m_asl", "wind_u_mps"]
    ].to_numpy(),

    wind_v = weather[
        ["height_m_asl", "wind_v_mps"]
    ].to_numpy(),
)

print("\nERA5 weather loaded into RocketPy!")
print(f"ERA5 data time: {selected_dt} UTC")
print(f"Launch time: {launch} UTC")
print(f"Atmospheric levels: {len(weather)}")

simulation_title = (
    f"ERA5 {selected_date} 19UTC - "
    f"{simulation_title}"
)


drag_on = pd.read_csv(
    folder / "CSTLV11_power_on_drag.csv",
    header=None,
    names=["mach", "cd"]
)

drag_off = pd.read_csv(
    folder / "CSTLV11_power_off_drag.csv",
    header=None,
    names=["mach", "cd"]
)

power_on_drag_func = Function(
    source=drag_on[["mach", "cd"]].to_numpy(),
    inputs="Mach",
    outputs="Drag Coefficient",
    interpolation="linear",
    extrapolation="constant",
)

power_off_drag_func = Function(
    source=drag_off[["mach", "cd"]].to_numpy(),
    inputs="Mach",
    outputs="Drag Coefficient",
    interpolation="linear",
    extrapolation="constant",
)

V11 = Rocket(
    mass = 6.525,
    radius = 0.127/2.0,
    inertia = (2.016, 2.016, 0.015),
    power_off_drag = power_off_drag_func,
    power_on_drag = power_on_drag_func,
    center_of_mass_without_motor = 1.053,
    coordinate_system_orientation = "nose_to_tail",
)

nosecone = V11.add_nose(
    kind = "ogive",
    length = 0.419,
    base_radius = 0.102/2.0,
    position = 0,
)

fins = V11.add_trapezoidal_fins(
    n = 4,
    root_chord = 0.229,
    tip_chord = 0.089,
    position = 1.64,
    cant_angle = 0,
    sweep_length = 0.185,
    radius = 0.127/2.0,
    span = 0.102,
)

canard1 = TrapezoidalFin(
    angular_position = 0,
    root_chord = 0.025,
    tip_chord = 0,
    sweep_length = 0.025,
    rocket_radius = 0.102/2.0,
    cant_angle = 0,
    span = 0.03,
)

canard2 = TrapezoidalFin(
    angular_position = 180,
    root_chord = 0.025,
    tip_chord = 0,
    sweep_length = 0.025,
    rocket_radius = 0.102/2.0,
    cant_angle = 0,
    span = 0.03,
)

V11.add_surfaces(
    [canard1, canard2],
    positions = 0.47,
)

boattail = V11.add_tail(
    top_radius = 0.127/2.0,
    bottom_radius = 0.102/2.0,
    length = 0.064,
    position = 1.64 + 0.229,
    name = "Boattail",
)

spincan_transition = V11.add_tail(
    top_radius = 0.102/2.0,
    bottom_radius = 0.127/2.0,
    length = 0.102,
    position = 1.627 - 0.102,
    name = "Spincan Transition",
)

drogue_radius = 0.762/2.0
drogue_cd = 1.4

drogue = V11.add_parachute(
    name = "Drogue Parachute",
    cd_s = drogue_cd * pi * drogue_radius**2,
    trigger = "apogee",
    sampling_rate = 100,
    lag = 0,
    noise = (0, 0, 0),
    radius = drogue_radius,
    drag_coefficient = drogue_cd,
)

main_radius = 1.52/2.0
main_cd = 1.4

main = V11.add_parachute(
    name = "Main Parachute",
    cd_s = main_cd * pi * main_radius**2,
    trigger = 457,
    sampling_rate = 100,
    lag = 0,
    noise = (0, 0, 0),
    radius = main_radius,
    drag_coefficient = main_cd,
)

rail_buttons = V11.set_rail_buttons(
    upper_button_position = 0.705,
    lower_button_position = 1.89,
    angular_position = 0,
)

L910 = SolidMotor(
    thrust_source = str(folder / "Cesaroni_2856L910-P.eng"),
    nozzle_position = 0,
    coordinate_system_orientation = "nozzle_to_combustion_chamber",
    dry_mass = 1.05444741,
    center_of_dry_mass_position = 0.16659244,
    dry_inertia = (0.01791230, 0.01791211, 0.00112808),
    nozzle_radius = 0.04699/2.0,
    throat_radius = 0.02159/2.0,
    grain_number = 2,
    grain_density = 1740,
    grain_outer_radius = 0.0643/2.0,
    grain_initial_inner_radius = 0.01905/2.0,
    grain_initial_height = 0.1356,
    grain_separation = 0.0025,
    grains_center_of_mass_position =  0.19160964,
)

V11.add_motor(L910, position = 1.93)

# V11.draw(plane="yz")

CSTL = Flight(
    rocket = V11,
    environment = env,
    max_time_step = 0.001,
    rail_length = 6.1,
    inclination = 87, # 86 - 88
    heading = 35, # 30 - 40
)

# ---------------- SIMULATION RESULTS ----------------

# Output file in the same folder as your Python script
results_file = folder / "V11_Simulation_Results.txt"

# Flight times
apogee_time = CSTL.apogee_time
landing_time = CSTL.t_final
descent_time = landing_time - apogee_time

# Coordinates
landing_lat = CSTL.latitude(landing_time)
landing_lon = CSTL.longitude(landing_time)

apogee_lat = CSTL.latitude(apogee_time)
apogee_lon = CSTL.longitude(apogee_time)

# Format results
results = f"""
==================================================
Simulation: {simulation_title}
==================================================
ERA5 Observation (UTC):     {selected_dt:%Y-%m-%d %H:%M}
Launch Time (UTC):          {launch}
Landing Coordinates:       {landing_lat:.6f}, {landing_lon:.6f}
Apogee Coordinates:        {apogee_lat:.6f}, {apogee_lon:.6f}
Apogee Elevation ASL (m):  {CSTL.apogee:.2f}
Apogee Time (s):           {apogee_time:.2f}
Landing Time (s):          {landing_time:.2f}
Descent Time (s):          {descent_time:.2f}
Impact Velocity (m/s):     {CSTL.impact_velocity:.2f}
Maximum Velocity (m/s):    {CSTL.max_speed:.2f}
Maximum Mach:              {CSTL.max_mach_number:.3f}
==================================================
"""

# Display results in terminal
print(results)

# Append results to text file
with open(results_file, "a", encoding="utf-8") as file:
    file.write(results + "\n")

print(f"Results saved to: {results_file}")
