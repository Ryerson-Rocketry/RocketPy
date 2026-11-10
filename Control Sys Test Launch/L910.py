from rocketpy import SolidMotor
from pathlib import Path

folder = Path(__file__).resolve().parent

L910 = SolidMotor(
    thrust_source = (folder / "Cesaroni_2856L910-P.eng"),
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