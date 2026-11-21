from rocketpy import Environment, SolidMotor, Rocket, TrapezoidalFin, Flight, Function

# need launch time
# drag curves - done
# weather

import numpy as np
import pandas as pd
from pathlib import Path
from math import pi
import datetime
from zoneinfo import ZoneInfo
from rocketpy.simulation import FlightDataExporter
import webbrowser

lat = 42.70477
long = -77.19170
elev = 268.49


env = Environment(
    date = (2026, 11, 21, 14),
    timezone="America/New_York",
    latitude = lat,
    longitude = long,
    elevation = elev,
)

# WEATHER HERE:


import requests
from zoneinfo import ZoneInfo

folder = Path(__file__).resolve().parent

simulation_title = input("Enter simulation title: ")

safe_title = "".join(
    c if c.isalnum() or c in "-_" else "_"
    for c in simulation_title
).strip("_") or "Icarus_Simulation"

launch_local = datetime.datetime(
    2026, 11, 21, 14,
    tzinfo=ZoneInfo("America/New_York")
)

launch_dt = launch_local.astimezone(datetime.timezone.utc)
launch = launch_dt.strftime("%Y-%m-%dT%H:%M")

model = "ecmwf_ifs025"

levels = [
    1000, 925, 850, 700,
    600, 500, 400, 300,
    250, 200
]

variables = [
    "surface_pressure",
    "temperature_2m",
    "wind_speed_10m",
    "wind_direction_10m",
]

for level in levels:
    variables.extend([
        f"temperature_{level}hPa",
        f"wind_speed_{level}hPa",
        f"wind_direction_{level}hPa",
        f"geopotential_height_{level}hPa",
    ])

url = "https://single-runs-api.open-meteo.com/v1/forecast"

def get_weather(run):
    response = requests.get(
        url,
        params={
            "latitude": lat,
            "longitude": long,
            "elevation": elev,
            "run": run,
            "models": model,
            "forecast_days": 10,
            "timezone": "UTC",
            "wind_speed_unit": "ms",
            "hourly": ",".join(variables),
        },
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"ECMWF API error {response.status_code}: "
            f"{response.text[:300]}"
        )

    return response.json()["hourly"]

now = datetime.datetime.now(datetime.timezone.utc)

latest_cycle = now.replace(
    hour=(now.hour // 6) * 6,
    minute=0,
    second=0,
    microsecond=0,
)

data = None
run = None
run_dt = None

print("\nSearching for latest ECMWF forecast...")

for offset in range(12):

    candidate = latest_cycle - datetime.timedelta(
        hours=6 * offset
    )

    if candidate > launch_dt:
        continue

    candidate_run = candidate.strftime(
        "%Y-%m-%dT%H:%M"
    )

    print(f"Checking ECMWF run: {candidate_run} UTC")

    try:
        candidate_data = get_weather(candidate_run)

        if launch not in candidate_data["time"]:
            continue

        i = candidate_data["time"].index(launch)

        required = [
            "surface_pressure",
            "temperature_2m",
            "wind_speed_10m",
            "wind_direction_10m",
            "temperature_850hPa",
            "wind_speed_850hPa",
            "geopotential_height_850hPa",
        ]

        if any(
            key not in candidate_data
            or candidate_data[key][i] is None
            for key in required
        ):
            continue

        data = candidate_data
        run = candidate_run
        run_dt = candidate
        break

    except (requests.RequestException, RuntimeError,
            KeyError, ValueError) as e:
        print(f"Run unavailable: {e}")

if data is None:
    raise RuntimeError(
        "No recent ECMWF forecast covering launch time "
        "was found. Check API availability and launch date."
    )

lead_hours = (
    launch_dt - run_dt
).total_seconds() / 3600

print(f"\nSelected ECMWF run: {run} UTC")
print(f"Launch time: {launch} UTC")
print(f"Forecast lead: {lead_hours:.0f} hours")

i = data["time"].index(launch)

def components(speed, direction):
    angle = np.radians(direction)

    u = -speed * np.sin(angle)
    v = -speed * np.cos(angle)

    return u, v

surface_values = [
    data["surface_pressure"][i],
    data["temperature_2m"][i],
    data["wind_speed_10m"][i],
    data["wind_direction_10m"][i],
]

if any(pd.isna(x) for x in surface_values):
    raise ValueError("Missing ECMWF surface weather data")

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


for level in levels:

    z = data[f"geopotential_height_{level}hPa"][i]
    t = data[f"temperature_{level}hPa"][i]
    speed = data[f"wind_speed_{level}hPa"][i]
    direction = data[f"wind_direction_{level}hPa"][i]

    if any(pd.isna(x) for x in [z, t, speed, direction]):
        print(f"Skipping missing {level} hPa level")
        continue

    earth_radius = 6371000
    height = earth_radius * z / (earth_radius - z)

    if height <= elev:
        continue

    u, v = components(speed, direction)

    rows.append([
        height,
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

if len(weather) < 3:
    raise ValueError("Insufficient ECMWF atmospheric levels")


try:
    extra_response = requests.get(
        url,
        params={
            "latitude": lat,
            "longitude": long,
            "elevation": elev,
            "run": run,
            "models": model,
            "forecast_days": 10,
            "timezone": "UTC",
            "wind_speed_unit": "ms",
            "hourly": (
                "wind_speed_100m,"
                "wind_direction_100m"
            ),
        },
        timeout=60,
    )

    extra_response.raise_for_status()
    extra = extra_response.json()["hourly"]

    j = extra["time"].index(launch)

    speed = extra["wind_speed_100m"][j]
    direction = extra["wind_direction_100m"][j]

    if not pd.isna(speed) and not pd.isna(direction):

        height = elev + 100
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
            height,
            pressure,
            temperature,
            u,
            v,
        ]

        print("Added 100 m wind data")

except (requests.RequestException, KeyError,
        ValueError, TypeError) as e:
    print(f"100 m wind unavailable: {e}")

weather = weather.sort_values(
    "height_m_asl"
).reset_index(drop=True)

weather_file = folder / (
    f"{safe_title}_ECMWF_"
    f"{run_dt:%Y%m%d_%HUTC}.csv"
)

weather.to_csv(weather_file, index=False)

print("\nECMWF weather saved!")
print(f"Location: {weather_file.resolve()}")
print(f"Atmospheric levels: {len(weather)}")

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

print("\nECMWF weather loaded into RocketPy!")
print(f"Forecast run: {run} UTC")
print(f"Launch time: {launch} UTC")
print(f"Forecast lead: {lead_hours:.0f} hours")
print(f"Atmospheric levels: {len(weather)}")

folder = Path(__file__).resolve().parent

drag_data = pd.read_csv(folder / "icarus drag curve.csv")

velocity = pd.to_numeric(drag_data["P1"], errors="coerce")
drag_force = pd.to_numeric(drag_data["P2"], errors="coerce")

valid = velocity.notna() & drag_force.notna() & (velocity > 0)
velocity = velocity[valid]
drag_force = drag_force[valid]

radius = 0.1019556 / 2.0
area = pi * radius**2

rho = 1.225
speed_of_sound = 343 

mach = velocity / speed_of_sound
cd = (2 * drag_force) / (rho * velocity**2 * area)

drag_curve = pd.DataFrame({
    "mach": mach,
    "cd": cd
}).sort_values("mach")

drag_curve.to_csv(
    folder / "icarus_drag_corrected.csv",
    index = False,
    header = False
)

drag_off = pd.read_csv(
    folder / "icarus_drag_corrected.csv",
    header = None,
    names = ["mach", "cd"]
)

power_off_drag_func = Function(
    source = drag_off[["mach", "cd"]].to_numpy(),
    inputs = "Mach",
    outputs = "Drag Coefficient",
    interpolation = "linear",
    extrapolation = "constant",
)

power_on_drag_func = Function(
    source = drag_off[["mach", "cd"]].to_numpy(),
    inputs = "Mach",
    outputs = "Drag Coefficient",
    interpolation = "linear",
    extrapolation = "constant",
)

Icarus = Rocket(
    mass = 11.25103225,
    radius = 0.1019556/2.0,
    inertia = (2.59801430, 2.59809153, 0.02052416),
    power_off_drag = power_off_drag_func,
    power_on_drag = power_on_drag_func,
    center_of_mass_without_motor = 1.03526436,
    coordinate_system_orientation = "nose_to_tail",
)

nosecone = Icarus.add_nose(
    kind = "ogive",
    length = 0.4140617,
    base_radius = 0.1019556/2.0,
    position = 0,
)

fins = Icarus.add_trapezoidal_fins(
    n = 4,
    root_chord = 0.2286,
    tip_chord = 0.0889,
    position = 1.64215937,
    cant_angle = 0,
    sweep_length = 0.1855762,
    radius = 0.127/2.0,
    span = 0.1016,
)

canard1 = TrapezoidalFin(
    angular_position = 0,
    root_chord = 0.03734919,
    tip_chord = 0,
    sweep_length = 0.03734919,
    rocket_radius = 0.1019556/2.0,
    cant_angle = 0,
    span = 0.01865231,
)

canard2 = TrapezoidalFin(
    angular_position = 180,
    root_chord = 0.03734919,
    tip_chord = 0,
    sweep_length = 0.03734919,
    rocket_radius = 0.1019556/2.0,
    cant_angle = 0,
    span = 0.01865231,
)

Icarus.add_surfaces(
    [canard1, canard2],
    positions = 0.45766779,
)

boattail = Icarus.add_tail(
    top_radius = 0.127/2.0,
    bottom_radius = 0.1019556/2.0,
    length = 0.0698516,
    position = 1.8707517,
    name = "Boattail",
)

spincan_transition = Icarus.add_tail(
    top_radius = 0.1019556/2.0,
    bottom_radius = 0.127/2.0,
    length = 0.1033526,
    position = 1.5405517,
    name = "Spincan Transition",
)

drogue_radius = 0.762/2.0
drogue_cd = 1.4

drogue = Icarus.add_parachute(
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

main = Icarus.add_parachute(
    name = "Main Parachute",
    cd_s = main_cd * pi * main_radius**2,
    trigger = 457,
    sampling_rate = 100,
    lag = 0,
    noise = (0, 0, 0),
    radius = main_radius,
    drag_coefficient = main_cd,
)

rail_buttons = Icarus.set_rail_buttons(
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

Icarus.add_motor(L910, position = 1.9660525)

# Icarus.draw(plane="yz")

test_launch = Flight(
    rocket = Icarus,
    environment = env,
    max_time_step = 0.001,
    rail_length = 6.1, 
    inclination = 87, # 86 - 88
    heading = 35, # 30 - 40
)

results_file = folder / "Icarus_Simulation_Results.txt"

apogee_time = test_launch.apogee_time
landing_time = test_launch.t_final

landing_lat = test_launch.latitude(landing_time)
landing_lon = test_launch.longitude(landing_time)

apogee_agl = test_launch.apogee - env.elevation

landing_distance = np.hypot(
    test_launch.x_impact,
    test_launch.y_impact
)

results = f"""
==================================================
Simulation: {simulation_title}
ECMWF Run (UTC):       {run}
Launch Time (UTC):     {launch}
==================================================
Apogee AGL (m):        {apogee_agl:.2f}
Maximum Velocity (m/s): {test_launch.max_speed:.2f}
Maximum Mach:          {test_launch.max_mach_number:.3f}
Time to Apogee (s):    {apogee_time:.2f}
Landing Time (s):      {landing_time:.2f}
Descent Time (s):      {landing_time - apogee_time:.2f}
Impact Velocity (m/s): {test_launch.impact_velocity:.2f}
Landing Distance (m):  {landing_distance:.2f}
Landing Coordinates:   {landing_lat:.6f}, {landing_lon:.6f}
==================================================
"""

print(results)

with open(results_file, "a", encoding="utf-8") as file:
    file.write(results + "\n")

print(f"Results saved to: {results_file}")


# Directions

directions_url = (
    "https://www.google.com/maps/dir/?api=1"
    f"&origin={lat},{long}"
    f"&destination={landing_lat},{landing_lon}"
    "&travelmode=walking"
)

directions_file = folder / "Icarus_Landing_Directions.txt"

with open(directions_file, "w", encoding="utf-8") as file:
    file.write(f"Launch: {lat}, {long}\n")
    file.write(f"Landing: {landing_lat}, {landing_lon}\n")
    file.write(f"Directions: {directions_url}\n")

print(f"Google Maps: {directions_url}")

webbrowser.open(directions_url)

# KML

kml_file = folder / "Icarus_Trajectory.kml"

FlightDataExporter(test_launch).export_kml(
    file_name=str(kml_file),
    extrude=True,
    altitude_mode="relativetoground",
)
