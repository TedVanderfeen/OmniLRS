__author__ = "Antoine Richard"
__copyright__ = "Copyright 2023-24, Space Robotics Lab, SnT, University of Luxembourg, SpaceR"
__license__ = "BSD 3-Clause"
__version__ = "2.0.0"
__maintainer__ = "Antoine Richard"
__email__ = "antoine.richard@uni.lu"
__status__ = "development"

from scipy.spatial.transform import Rotation as SSTR
from typing import List, Tuple
import omni.kit.actions.core
import math
import os

from omni.isaac.core.utils.stage import add_reference_to_stage
import omni

from pxr import UsdLux, Gf, Usd

from src.terrain_management.large_scale_terrain_manager import LargeScaleTerrainManager
from src.configurations.large_scale_terrain_confs import LargeScaleTerrainConf
from src.terrain_management.large_scale_terrain.pxr_utils import set_xform_ops
from src.configurations.stellar_engine_confs import StellarEngineConf, SunConf
from src.stellar.stellar_engine import StellarEngine
from src.environments.base_env import BaseEnv
from src.robots.robot import RobotManager
from assets import get_assets_path


class LargeScaleController(BaseEnv):
    """
    This class is used to control the environment's interactive elements.
    """

    def __init__(
        self,
        large_scale_settings: LargeScaleTerrainConf = None,
        stellar_engine_settings: StellarEngineConf = None,
        sun_settings: SunConf = None,
        **kwargs,
    ) -> None:
        """
        Initializes the env controller. This class is used to control the env interactive elements.
        Including:
            - Sun position, intensity, radius, color.

        Args:
            env_settings (LargeScaleTerrainConf): The settings of the lab.
            stellar_engine_settings (StellarEngineConf): The settings of the stellar engine.
            sun_settings (SunConf): The settings of the sun.
            **kwargs: Arbitrary keyword arguments.
        """

        super().__init__(**kwargs)
        self.stage_settings = large_scale_settings
        self.sun_settings = sun_settings
        if stellar_engine_settings is not None:
            self.SE = StellarEngine(stellar_engine_settings)
            self.enable_stellar_engine = True
        else:
            self.enable_stellar_engine = False
        self.dem = None
        self.mask = None
        self.scene_name = "/LargeScaleLunar"

    def build_scene(self) -> None:
        """
        Builds the scene.
        """

        # Creates an empty xform with the name lunaryard
        large_scale = self.stage.DefinePrim(self.scene_name, "Xform")

        # Creates the sun
        sun = self.stage.DefinePrim(os.path.join(self.scene_name, "sun"), "Xform")
        self._sun_prim = sun.GetPrim()
        light: UsdLux.DistantLight = UsdLux.DistantLight.Define(self.stage, os.path.join(self.scene_name, "Sun", "sun"))
        self._sun_lux: Usd.Prim = light.GetPrim()
        light.CreateIntensityAttr(self.sun_settings.intensity)
        light.CreateAngleAttr(self.sun_settings.angle)
        light.CreateDiffuseAttr(self.sun_settings.diffuse_multiplier)
        light.CreateSpecularAttr(self.sun_settings.specular_multiplier)
        light.CreateColorAttr(
            Gf.Vec3f(self.sun_settings.color[0], self.sun_settings.color[1], self.sun_settings.color[2])
        )
        light.CreateColorTemperatureAttr(self.sun_settings.temperature)
        x, y, z, w = SSTR.from_euler(
            "xyz", [0, self.sun_settings.elevation, self.sun_settings.azimuth - 90], degrees=True
        ).as_quat()
        set_xform_ops(light.GetPrim(), Gf.Vec3d(0, 0, 0), Gf.Quatd(w, Gf.Vec3d(x, y, z)), Gf.Vec3d(1, 1, 1))

        # Creates the earth
        earth = self.stage.DefinePrim(os.path.join(self.scene_name, "Earth"), "Xform")
        self._earth_prim = earth.GetPrim().GetReferences().AddReference(self.stage_settings.earth_usd_path)
        dist = self.stage_settings.earth_distance * self.stage_settings.earth_scale
        px = math.cos(math.radians(self.stage_settings.earth_azimuth)) * dist
        py = math.sin(math.radians(self.stage_settings.earth_azimuth)) * dist
        pz = math.sin(math.radians(self.stage_settings.earth_altitude)) * dist
        set_xform_ops(self._earth_prim, Gf.Vec3d(px, py, pz), Gf.Quatd(0, 0, 0, 1))

    def instantiate_scene(self) -> None:
        """
        Instantiates the scene. Applies any operations that need to be done after the scene is built and
        the renderer has been stepped.
        """

        pass

    def reset(self) -> None:
        """
        Resets the environment. Implement the logic to reset the environment.
        """

        pass

    def update(self) -> None:
        """
        Updates the environment.
        """

        pass

    def load(self) -> None:
        """
        Loads the lab interactive elements in the stage.
        Creates the instancer for the rocks, and generates the terrain.
        """

        self.build_scene()
        # Instantiates the terrain manager
        self.LSTM = LargeScaleTerrainManager(self.stage_settings)
        self.LSTM.build()
        # Sets the sun using the stellar engine if enabled
        if self.enable_stellar_engine:
            self.SE.set_lat_lon(*self.LSTM.get_lat_lon())
        # Fetches the interactive elements
        self.collect_interactive_assets()

    def add_robot_manager(self, robotManager: RobotManager) -> None:
        """
        Adds the robot manager to the environment.

        Args:
            robotManager (RobotManager): The robot manager to be added.
        """

        self.robotManager = robotManager

    def get_lux_assets(self, prim: "Usd.Prim") -> None:
        """
        Returns the UsdLux prims under a given prim.

        Args:
            prim (Usd.Prim): The prim to be searched.

        Returns:
            list: A list of UsdLux prims.
        """

        lights = []
        for prim in Usd.PrimRange(prim):
            if prim.IsA(UsdLux.DistantLight):
                lights.append(prim)
            if prim.IsA(UsdLux.SphereLight):
                lights.append(prim)
            if prim.IsA(UsdLux.CylinderLight):
                lights.append(prim)
            if prim.IsA(UsdLux.DiskLight):
                lights.append(prim)
        return lights

    # ==============================================================================
    # Stellar engine control
    # ==============================================================================

    def set_coordinates(self, latlong: Tuple[float, float] = (0.0, 0.0)) -> None:
        """
        Sets the coordinates of the lab.

        Args:
            latlong (Tuple[float,float]): The latitude and longitude of the scene on the moon.
        """

        if self.enable_stellar_engine:
            self.SE.set_lat_lon(latlong[1], latlong[0])

    def set_time(self, time: float = 0.0) -> None:
        """
        Sets the time of the stellar engine.

        Args:
            time (float): The time in seconds.
        """

        if self.enable_stellar_engine:
            self.SE.set_time(time)

    def set_time_scale(self, scale: float = 1.0) -> None:
        """
        Sets the time scale of the stellar engine.

        Args:
            scale (float): The time scale.
        """

        if self.enable_stellar_engine:
            self.SE.set_time_scale(scale)

    def update_stellar_engine(self, dt: float = 0.0) -> None:
        """
        Updates the sun and earth pose.

        Args:
            dt (float): The time step.
        """

        if self.enable_stellar_engine:
            update = self.SE.update(dt)
            if update:
                earth_pos = self.SE.get_local_position("earth")
                alt, az, _ = self.SE.get_alt_az("sun")
                quat = self.SE.convert_alt_az_to_quat(alt, az)

                self.set_sun_pose(((0, 0, 0), quat))
                self.set_earth_pose((earth_pos, (0, 0, 0, 1)))

    # ==============================================================================
    # Earth control
    # ==============================================================================

    def set_earth_pose(
        self,
        position: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        orientation: Tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0),
    ) -> None:
        """
        Sets the pose of the earth.

        Args:
            position (Tuple[float,float,float]): The position of the earth. In meters. (x,y,z)
            orientation (Tuple[float,float,float,float]): The orientation of the earth. (w,x,y,z)
        """

        w, x, y, z = (orientation[0], orientation[1], orientation[2], orientation[3])
        x, y, z = (position[0], position[1], position[2])
        set_xform_ops(self._earth_prim, position=Gf.Vec3d(x, y, z), orientation=Gf.Quatd(w, Gf.Vec3d(x, y, z)))

    # ==============================================================================
    # Sun control
    # ==============================================================================
    def set_sun_pose(
        self,
        position: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        orientation: Tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0),
    ) -> None:
        """
        Sets the pose of the sun.

        Args:
            position (Tuple[float,float,float]): The position of the sun. In meters. (x,y,z)
            orientation (Tuple[float,float,float,float]): The orientation of the sun. (w,x,y,z)
        """

        w, x, y, z = (orientation[0], orientation[1], orientation[2], orientation[3])
        set_xform_ops(self._sun_prim, orientation=Gf.Quatd(w, Gf.Vec3d(x, y, z)))

    def set_sun_intensity(self, intensity: float) -> None:
        """
        Sets the intensity of the sun.

        Args:
            intensity (float): The intensity of the projector (arbitrary unit).
        """

        self._sun_lux.GetAttribute("intensity").Set(intensity)

    def set_sun_color(self, color: List[float]) -> None:
        """
        Sets the color of the projector.

        Args:
            color (List[float]): The color of the projector (RGB).
        """

        color = Gf.Vec3d(color[0], color[1], color[2])
        self.set_attribute_batch(self._projector_lux, "color", color)

    def set_sun_angle(self, angle: float) -> None:
        """
        Sets the angle of the sun. Larger values make the sun larger, and soften the shadows.

        Args:
            angle (float): The angle of the projector.
        """

        self.set_attribute_batch(self._projector_lux, "angle", angle)

    # ==============================================================================
    # Terrain info
    # ==============================================================================

    def get_height_and_normal(
        self, position: Tuple[float, float, float]
    ) -> Tuple[float, float, float, float, float, float]:
        """
        Gets the height and normal of the terrain at a given position.

        Args:
            position (Tuple[float,float,float]): The position in meters.

        Returns:
            Tuple[float,float,float,float,float,float]: The height and normal of the terrain at the given position.
        """

        return self.LSTM.get_height_and_normal(position)

    def deform_derrain(self) -> None:
        """
        Deforms the terrain.
        Args:
            world_poses (np.ndarray): The world poses of the contact points.
            contact_forces (np.ndarray): The contact forces in local frame reported by rigidprimview.
        """
        pass

    def apply_terramechanics(self) -> None:
        pass
