from rocketpy import Environment, SolidMotor, Rocket, TrapezoidalFin, Flight, Function

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

launch_hour = 14  # 2 pm

env = Environment(
    date = (2026, 11, 21, launch_hour),
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
    2026, 11, 21, launch_hour,
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

import matplotlib.pyplot as plt
from xml.etree import ElementTree as ET

# Settings
n_simulations = 100
rng = np.random.default_rng(42)

# Uncertainty assumptions (1 standard deviation)
wind_speed_std = 0.10       # 10%
wind_direction_std = 10.0   # degrees
wind_component_std = 1.0    # m/s
inclination_std = 1.0       # degrees
heading_std = 2.0           # degrees

# Original ECMWF atmospheric profile
heights = weather["height_m_asl"].to_numpy()
wind_u = weather["wind_u_mps"].to_numpy()
wind_v = weather["wind_v_mps"].to_numpy()

pressure = weather[
    ["height_m_asl", "pressure_pa"]
].to_numpy()

temperature = weather[
    ["height_m_asl", "temperature_k"]
].to_numpy()

results_mc = []

print(f"\nStarting {n_simulations} Monte Carlo simulations...")

for j in range(n_simulations):

    # Randomize wind speed and direction
    speed_factor = max(
        0.0,
        rng.normal(1.0, wind_speed_std)
    )

    angle = np.radians(
        rng.normal(0.0, wind_direction_std)
    )

    # Rotate horizontal wind vector
    u_new = speed_factor * (
        wind_u * np.cos(angle) +
        wind_v * np.sin(angle)
    )

    v_new = speed_factor * (
        -wind_u * np.sin(angle) +
        wind_v * np.cos(angle)
    )

    # Add wind-component uncertainty
    u_new += rng.normal(0, wind_component_std)
    v_new += rng.normal(0, wind_component_std)

    # Create randomized atmospheric environment
    mc_env = Environment(
        date=(2026, 11, 21, launch_hour),
        timezone="America/New_York",
        latitude=lat,
        longitude=long,
        elevation=elev,
    )

    mc_env.set_atmospheric_model(
        type="custom_atmosphere",
        pressure=pressure,
        temperature=temperature,
        wind_u=np.column_stack((heights, u_new)),
        wind_v=np.column_stack((heights, v_new)),
    )

    # Randomize launch rail orientation
    inclination_mc = rng.normal(87, inclination_std)
    heading_mc = rng.normal(35, heading_std)

    try:
        flight_mc = Flight(
            rocket=Icarus,
            environment=mc_env,
            rail_length=6.1,
            inclination=inclination_mc,
            heading=heading_mc,
            max_time_step=0.02,
        )

        t = flight_mc.t_final

        results_mc.append({
            "simulation": j + 1,
            "latitude": float(flight_mc.latitude(t)),
            "longitude": float(flight_mc.longitude(t)),
            "x_m": float(flight_mc.x_impact),
            "y_m": float(flight_mc.y_impact),
            "apogee_agl_m": float(
                flight_mc.apogee - elev
            ),
            "inclination_deg": inclination_mc,
            "heading_deg": heading_mc,
        })

    except Exception as e:
        print(f"Simulation {j + 1} failed: {e}")

    if (j + 1) % 10 == 0:
        print(f"Completed {j + 1}/{n_simulations}")

# ---------------- SAVE LANDING COORDINATES ----------------

if len(results_mc) < 3:
    raise RuntimeError("Not enough successful Monte Carlo runs")

mc = pd.DataFrame(results_mc)

csv_file = folder / f"{safe_title}_MC_Landings.csv"
mc.to_csv(csv_file, index=False)

# Nominal landing point
nominal_x = float(test_launch.x_impact)
nominal_y = float(test_launch.y_impact)

# Calculate dispersion
mean_x = mc["x_m"].mean()
mean_y = mc["y_m"].mean()

distance_from_nominal = np.hypot(
    mc["x_m"] - nominal_x,
    mc["y_m"] - nominal_y,
)

print("\n========== MONTE CARLO RESULTS ==========")
print(f"Successful flights: {len(mc)}")
print(f"Mean landing: {mc['latitude'].mean():.6f}, "
      f"{mc['longitude'].mean():.6f}")
print(f"Mean east offset: {mean_x:.1f} m")
print(f"Mean north offset: {mean_y:.1f} m")
print(f"Average distance from nominal: "
      f"{distance_from_nominal.mean():.1f} m")
print(f"95th percentile distance from nominal: "
      f"{np.percentile(distance_from_nominal, 95):.1f} m")
print(f"Maximum distance from nominal: "
      f"{distance_from_nominal.max():.1f} m")
print(f"Coordinates saved: {csv_file}")



# ---------------- MONTE CARLO KML ----------------

from scipy.spatial import cKDTree
from xml.etree import ElementTree as ET

# Landing coordinates relative to launch site (metres)
points = mc[["x_m", "y_m"]].to_numpy()

if len(points) < 3:
    raise ValueError("At least 3 landing points required")

# ---------------- FIND DENSEST LANDING AREA ----------------

n_core = max(2, int(np.ceil(len(points) * 0.50)))

tree = cKDTree(points)
distances, indices = tree.query(points, k=n_core)

# Centre of the most concentrated 50% of landings
core_index = np.argmin(distances[:, -1])
center_x, center_y = points[core_index]

# Distances from the selected centre
radial_distances = np.hypot(
    points[:, 0] - center_x,
    points[:, 1] - center_y
)

# Radii containing 50% and 95% of simulations
radius_50 = np.sort(radial_distances)[
    int(np.ceil(len(points) * 0.50)) - 1
]

radius_95 = np.sort(radial_distances)[
    int(np.ceil(len(points) * 0.95)) - 1
]

print("\n========== LANDING DISPERSION ==========")
print(f"Successful runs: {len(mc)}")
print(f"50% landing radius: {radius_50:.1f} m")
print(f"95% landing radius: {radius_95:.1f} m")
print(f"Nominal landing: {landing_lat:.6f}, {landing_lon:.6f}")


# ---------------- CONVERT METRES TO GPS ----------------

earth_radius = 6371000.0

def to_gps(x, y):
    latitude = lat + np.degrees(y / earth_radius)
    longitude = long + np.degrees(
        x / (earth_radius * np.cos(np.radians(lat)))
    )
    return latitude, longitude


# ---------------- CREATE KML ----------------

ns = "http://www.opengis.net/kml/2.2"
ET.register_namespace("", ns)

kml = ET.Element(f"{{{ns}}}kml")
document = ET.SubElement(kml, f"{{{ns}}}Document")

ET.SubElement(
    document, f"{{{ns}}}name"
).text = f"Icarus Monte Carlo - {simulation_title}"


# ---------------- ADD STYLES ----------------

def add_style(style_id, color, scale=1.0):
    style = ET.SubElement(
        document, f"{{{ns}}}Style",
        id=style_id
    )

    icon_style = ET.SubElement(
        style, f"{{{ns}}}IconStyle"
    )

    ET.SubElement(
        icon_style, f"{{{ns}}}color"
    ).text = color

    ET.SubElement(
        icon_style, f"{{{ns}}}scale"
    ).text = str(scale)

    icon = ET.SubElement(
        icon_style, f"{{{ns}}}Icon"
    )

    ET.SubElement(
        icon, f"{{{ns}}}href"
    ).text = (
        "http://maps.google.com/mapfiles/kml/"
        "shapes/placemark_circle.png"
    )


add_style("landing", "ffff0000", 0.5)   # Blue
add_style("nominal", "ff00ff00", 1.3)   # Green


# ---------------- CIRCLE FUNCTION ----------------

def add_circle(name, radius, line_color, fill_color):

    placemark = ET.SubElement(
        document, f"{{{ns}}}Placemark"
    )

    ET.SubElement(
        placemark, f"{{{ns}}}name"
    ).text = name

    style = ET.SubElement(
        placemark, f"{{{ns}}}Style"
    )

    line_style = ET.SubElement(
        style, f"{{{ns}}}LineStyle"
    )

    ET.SubElement(
        line_style, f"{{{ns}}}color"
    ).text = line_color

    ET.SubElement(
        line_style, f"{{{ns}}}width"
    ).text = "3"

    poly_style = ET.SubElement(
        style, f"{{{ns}}}PolyStyle"
    )

    ET.SubElement(
        poly_style, f"{{{ns}}}color"
    ).text = fill_color

    polygon = ET.SubElement(
        placemark, f"{{{ns}}}Polygon"
    )

    ET.SubElement(
        polygon, f"{{{ns}}}tessellate"
    ).text = "1"

    outer = ET.SubElement(
        polygon, f"{{{ns}}}outerBoundaryIs"
    )

    ring = ET.SubElement(
        outer, f"{{{ns}}}LinearRing"
    )

    coordinates = []

    for angle in np.linspace(0, 2 * np.pi, 181):

        x = center_x + radius * np.cos(angle)
        y = center_y + radius * np.sin(angle)

        latitude, longitude = to_gps(x, y)

        coordinates.append(
            f"{longitude:.8f},{latitude:.8f},0"
        )

    ET.SubElement(
        ring, f"{{{ns}}}coordinates"
    ).text = " ".join(coordinates)


# ---------------- LANDING CIRCLES ----------------

# Red outer circle: 95% of landings
add_circle(
    f"95% Landing Area - {radius_95:.0f} m radius",
    radius_95,
    "ff0000ff",  # Red outline
    "220000ff",  # Transparent red fill
)

# Yellow inner circle: 50% of landings
add_circle(
    f"50% Landing Area - {radius_50:.0f} m radius",
    radius_50,
    "ff00ffff",  # Yellow outline
    "4400ffff",  # Transparent yellow fill
)


# ---------------- ALL MONTE CARLO LANDING DOTS ----------------

landings_folder = ET.SubElement(
    document, f"{{{ns}}}Folder"
)

ET.SubElement(
    landings_folder, f"{{{ns}}}name"
).text = "Monte Carlo Landing Points"

for _, row in mc.iterrows():

    placemark = ET.SubElement(
        landings_folder, f"{{{ns}}}Placemark"
    )

    ET.SubElement(
        placemark, f"{{{ns}}}name"
    ).text = f"Landing {int(row['simulation'])}"

    ET.SubElement(
        placemark, f"{{{ns}}}styleUrl"
    ).text = "#landing"

    point = ET.SubElement(
        placemark, f"{{{ns}}}Point"
    )

    ET.SubElement(
        point, f"{{{ns}}}coordinates"
    ).text = (
        f"{row['longitude']:.8f},"
        f"{row['latitude']:.8f},0"
    )


# ---------------- NOMINAL LANDING DOT ----------------

placemark = ET.SubElement(
    document, f"{{{ns}}}Placemark"
)

ET.SubElement(
    placemark, f"{{{ns}}}name"
).text = "Nominal Landing"

ET.SubElement(
    placemark, f"{{{ns}}}styleUrl"
).text = "#nominal"

point = ET.SubElement(
    placemark, f"{{{ns}}}Point"
)

ET.SubElement(
    point, f"{{{ns}}}coordinates"
).text = f"{landing_lon:.8f},{landing_lat:.8f},0"


# ---------------- SAVE KML ----------------

mc_kml_file = folder / f"{safe_title}_MC_Dispersion.kml"

ET.ElementTree(kml).write(
    mc_kml_file,
    encoding="utf-8",
    xml_declaration=True,
)

print(f"Monte Carlo KML saved: {mc_kml_file.resolve()}")

print(f"CG at launch: {Icarus.center_of_mass(0):.4f} m")
print(f"CP at Mach 0: {Icarus.cp_position(0):.4f} m")
print(f"Initial stability: {Icarus.static_margin(0):.3f} cal")