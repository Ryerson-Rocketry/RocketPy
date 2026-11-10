from rocketpy import Environment, SolidMotor, Rocket, TrapezoidalFin, Flight, Function

import numpy as np
import pandas as pd
from pathlib import Path
from math import pi
import datetime

lat = 42.70477
long = -77.19170
elev = 268.49

env = Environment(
    date = (2026, 11, 13, 14),
    timezone="America/New_York",
    latitude = lat,
    longitude = long,
    elevation = elev,
)

# WEATHER HERE:

import requests

folder = Path(__file__).resolve().parent

simulation_title = input("Enter simulation title: ")

safe_title = "".join(
    c if c.isalnum() or c in "-_" else "_"
    for c in simulation_title
).strip("_") or "Simulation"

# CHANGE THIS FOR EACH TEST
# earliest is 43 hrs before
run = "2026-11-12T00:00"

# KEEP LAUNCH TIME THE SAME
launch = "2026-11-13T19:00"

# Check HRRR forecast range
run_dt = datetime.datetime.fromisoformat(run)
launch_dt = datetime.datetime.fromisoformat(launch)
lead_hours = (launch_dt - run_dt).total_seconds() / 3600

max_lead = 48 if run_dt.hour in [0, 6, 12, 18] else 18

if not 0 <= lead_hours <= max_lead:
    raise ValueError(
        f"HRRR forecast unavailable: {lead_hours:.0f}h "
        f"requested, maximum is {max_lead}h"
    )

# Pressure levels available for the profile
levels = [925, 850, 700, 500]

variables = [
    "surface_pressure",
    "temperature_2m",
    "wind_speed_10m",
    "wind_direction_10m",
]

for level in levels:
    variables += [
        f"temperature_{level}hPa",
        f"wind_speed_{level}hPa",
        f"wind_direction_{level}hPa",
        f"geopotential_height_{level}hPa",
    ]

url = "https://single-runs-api.open-meteo.com/v1/forecast"

# Request a specific archived HRRR model run
def get_weather(requested_variables):
    response = requests.get(
        url,
        params={
            "latitude": lat,
            "longitude": long,
            "elevation": elev,
            "run": run,
            "models": "ncep_hrrr_conus",
            "forecast_days": 3,
            "timezone": "UTC",
            "wind_speed_unit": "ms",
            "hourly": ",".join(requested_variables),
        },
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"HRRR API error {response.status_code}: "
            f"{response.text[:500]}"
        )

    return response.json()["hourly"]


print("Downloading HRRR weather...")

data = get_weather(variables)

if launch not in data["time"]:
    raise ValueError(
        "Launch time not found in this HRRR forecast run"
    )

i = data["time"].index(launch)


# Convert meteorological wind direction to U and V
def components(speed, direction):
    angle = np.radians(direction)

    u = -speed * np.sin(angle)
    v = -speed * np.cos(angle)

    return u, v


# surface

u, v = components(
    data["wind_speed_10m"][i],
    data["wind_direction_10m"][i],
)

rows = [[
    elev,
    data["surface_pressure"][i] * 100,
    data["temperature_2m"][i] + 273.15,
    u,
    v,
]]


# pressure

for level in levels:

    z = data[f"geopotential_height_{level}hPa"][i]
    t = data[f"temperature_{level}hPa"][i]
    speed = data[f"wind_speed_{level}hPa"][i]
    direction = data[f"wind_direction_{level}hPa"][i]

    if any(pd.isna(x) for x in [z, t, speed, direction]):
        raise ValueError(
            f"Missing HRRR data at {level} hPa"
        )

    if z <= elev:
        continue

    u, v = components(speed, direction)

    rows.append([
        z,
        level * 100,
        t + 273.15,
        u,
        v,
    ])


weather = pd.DataFrame(
    rows,
    columns=[
        "height_m_asl",
        "pressure_pa",
        "temperature_k",
        "wind_u_mps",
        "wind_v_mps",
    ],
).sort_values("height_m_asl").reset_index(drop=True)


# extra
# Try HRRR's 80 m above-ground wind

try:
    extra = get_weather([
        "wind_speed_80m",
        "wind_direction_80m",
    ])

    j = extra["time"].index(launch)

    speed = extra["wind_speed_80m"][j]
    direction = extra["wind_direction_80m"][j]

    if not pd.isna(speed) and not pd.isna(direction):

        height = elev + 80
        u, v = components(speed, direction)

        pressure = np.interp(
            height,
            weather["height_m_asl"],
            weather["pressure_pa"],
        )

        temperature = np.interp(
            height,
            weather["height_m_asl"],
            weather["temperature_k"],
        )

        weather.loc[len(weather)] = [
            height, pressure, temperature, u, v
        ]

        print("Added 80 m wind data")

except (requests.RequestException, RuntimeError,
        KeyError, ValueError, TypeError) as e:
    print(f"80 m wind data unavailable: {e}")


weather = weather.sort_values(
    "height_m_asl"
).reset_index(drop=True)

if len(weather) < 3:
    raise ValueError("Insufficient HRRR atmospheric levels")

# Save before loading into sim

weather_file = folder / f"{safe_title}.csv"

weather.to_csv(weather_file, index=False)

print("\nHRRR weather file saved!")
print(f"Location: {weather_file.resolve()}")
print(f"File exists: {weather_file.exists()}")


# Use

env.set_atmospheric_model(
    type="custom_atmosphere",

    pressure=weather[
        ["height_m_asl", "pressure_pa"]
    ].to_numpy(),

    temperature=weather[
        ["height_m_asl", "temperature_k"]
    ].to_numpy(),

    wind_u=weather[
        ["height_m_asl", "wind_u_mps"]
    ].to_numpy(),

    wind_v=weather[
        ["height_m_asl", "wind_v_mps"]
    ].to_numpy(),
)

print("\nHRRR weather loaded into RocketPy!")
print(f"Forecast run: {run} UTC")
print(f"Launch time: {launch} UTC")
print(f"Forecast lead: {lead_hours:.0f} hours")
print(f"Atmospheric levels: {len(weather)}")

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