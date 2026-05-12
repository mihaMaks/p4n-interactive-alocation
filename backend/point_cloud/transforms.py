"""
Coordinate system transformations for point cloud processing.
Handles conversion between geographic (lat/lon) and projected coordinates.
"""
import numpy as np
from typing import List, Tuple, Optional
import warnings


class CoordinateTransformer:
    """Transform coordinates between different coordinate systems."""

    @staticmethod
    def wgs84_to_utm(lat: float, lon: float, zone: Optional[int] = None) -> Tuple[float, float]:
        """
        Convert WGS84 lat/lon to UTM coordinates.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            zone: UTM zone (auto-detected if None)

        Returns:
            Tuple of (easting, northing) in meters
        """
        try:
            import pyproj
        except ImportError:
            raise ImportError("pyproj is required for coordinate transformations. Install with: pip install pyproj")

        if zone is None:
            # Auto-detect UTM zone
            zone = int((lon + 180) / 6) + 1

        # Determine hemisphere
        hemisphere = 'north' if lat >= 0 else 'south'

        # Create transformer
        wgs84 = pyproj.CRS("EPSG:4326")  # WGS84
        utm_crs = pyproj.CRS(f"EPSG:326{zone:02d}") if hemisphere == 'north' else pyproj.CRS(f"EPSG:327{zone:02d}")

        transformer = pyproj.Transformer.from_crs(wgs84, utm_crs, always_xy=True)

        easting, northing = transformer.transform(lon, lat)
        return easting, northing

    @staticmethod
    def utm_to_wgs84(easting: float, northing: float, zone: int, hemisphere: str = 'north') -> Tuple[float, float]:
        """
        Convert UTM coordinates to WGS84 lat/lon.

        Args:
            easting: UTM easting in meters
            northing: UTM northing in meters
            zone: UTM zone number
            hemisphere: 'north' or 'south'

        Returns:
            Tuple of (lat, lon) in degrees
        """
        try:
            import pyproj
        except ImportError:
            raise ImportError("pyproj is required for coordinate transformations. Install with: pip install pyproj")

        utm_crs = pyproj.CRS(f"EPSG:326{zone:02d}") if hemisphere == 'north' else pyproj.CRS(f"EPSG:327{zone:02d}")
        wgs84 = pyproj.CRS("EPSG:4326")

        transformer = pyproj.Transformer.from_crs(utm_crs, wgs84, always_xy=True)

        lon, lat = transformer.transform(easting, northing)
        return lat, lon

    @staticmethod
    def transform_polygon_wgs84_to_utm(polygon: List[List[float]], zone: Optional[int] = None) -> List[List[float]]:
        """
        Transform a polygon from WGS84 lat/lon to UTM coordinates.

        Args:
            polygon: List of [lat, lon] coordinates
            zone: UTM zone (auto-detected from first point if None)

        Returns:
            List of [easting, northing] coordinates
        """
        if not polygon:
            return []

        # Use first point to determine UTM zone if not specified
        if zone is None:
            lat, lon = polygon[0]
            zone = int((lon + 180) / 6) + 1

        transformed = []
        for lat, lon in polygon:
            easting, northing = CoordinateTransformer.wgs84_to_utm(lat, lon, zone)
            transformed.append([easting, northing])

        return transformed

    @staticmethod
    def transform_polygon_wgs84_to_epsg(polygon: List[List[float]], epsg: int) -> List[List[float]]:
        """Transform polygon from WGS84 (lat/lon) to a target EPSG projected CRS."""
        if not polygon:
            return []

        try:
            import pyproj
        except ImportError:
            raise ImportError("pyproj is required for coordinate transformations. Install with: pip install pyproj")

        transformer = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
        transformed = []
        for lat, lon in polygon:
            x, y = transformer.transform(lon, lat)
            transformed.append([x, y])
        return transformed

    @staticmethod
    def detect_coordinate_system(points) -> str:
        """
        Attempt to detect the coordinate system of coordinates.

        Args:
            points: List of coordinates [x, y] or [lat, lon], or Nx2/Nx3 array

        Returns:
            String indicating likely coordinate system ('wgs84', 'utm', 'local', 'unknown')
        """
        if len(points) == 0:
            return 'unknown'

        # Convert to numpy array if not already
        import numpy as np
        points_array = np.array(points)

        # Handle both 2D and 3D coordinates
        if points_array.shape[1] >= 2:
            coords_2d = points_array[:, :2]  # Use only x,y or lat,lon
        else:
            return 'unknown'

        # Get bounds
        min_coords = coords_2d.min(axis=0)
        max_coords = coords_2d.max(axis=0)
        ranges = max_coords - min_coords

        # WGS84 lat/lon detection (degrees)
        # Latitude: -90 to 90, Longitude: -180 to 180
        if (min_coords[0] >= -90 and max_coords[0] <= 90 and
            min_coords[1] >= -180 and max_coords[1] <= 180):
            # Check if coordinates look like lat/lon (not too large ranges)
            if ranges[0] <= 10 and ranges[1] <= 10:  # Within 10 degrees
                return 'wgs84'

        # UTM detection (meters, typically 1000s to 100000s)
        if (min_coords[0] >= 100000 and max_coords[0] <= 1000000 and
            min_coords[1] >= 1000000 and max_coords[1] <= 10000000):
            return 'utm'

        # Local coordinate system (small ranges, around origin or small offsets)
        if ranges[0] <= 10000 and ranges[1] <= 10000:
            return 'local'

        return 'unknown'

    @staticmethod
    def suggest_transformation(
        source_coords: List[List[float]],
        target_system: str = 'utm',
        point_cloud_bounds: Optional[Tuple] = None,
    ) -> dict:
        """
        Suggest coordinate transformation based on input coordinates.

        Args:
            source_coords: List of [x, y] coordinates from user input
            target_system: Target coordinate system ('utm', 'wgs84')

        Returns:
            Dictionary with transformation suggestion
        """
        print(f"DEBUG: suggest_transformation called with source_coords: {source_coords}")
        print(f"DEBUG: source_coords type: {type(source_coords)}")
        print(f"DEBUG: source_coords length: {len(source_coords) if hasattr(source_coords, '__len__') else 'no len'}")
        
        # Check if it's a string that needs to be parsed
        if isinstance(source_coords, str):
            print(f"DEBUG: source_coords is a string, attempting to parse as JSON")
            try:
                import json
                source_coords = json.loads(source_coords)
                print(f"DEBUG: parsed source_coords: {source_coords}")
            except Exception as e:
                print(f"DEBUG: failed to parse string as JSON: {e}")
                raise ValueError(f"Invalid polygon format: {source_coords}")
        
        coords_array = np.array(source_coords)
        print(f"DEBUG: coords_array shape: {coords_array.shape}")
        print(f"DEBUG: coords_array: {coords_array}")

        # Detect input coordinate system
        detected_system = CoordinateTransformer.detect_coordinate_system(coords_array)
        print(f"DEBUG: detected_system: {detected_system}")

        suggestion = {
            'detected_input_system': detected_system,
            'suggested_transformation': None,
            'reasoning': '',
            'transformed_polygon': None
        }

        if detected_system == 'wgs84' and target_system == 'utm':
            # Convert WGS84 to projected CRS. If cloud bounds are known, choose CRS by bounds.
            try:
                transformed = None
                transformation_name = None

                if point_cloud_bounds is not None:
                    cloud_min, cloud_max = point_cloud_bounds

                    # Heuristic: Slovenian national projected CRS (EPSG:3794 / D96-TM)
                    # is typical when Y values are in low hundred-thousands rather than millions.
                    if cloud_max[1] < 1_000_000:
                        transformed = CoordinateTransformer.transform_polygon_wgs84_to_epsg(source_coords, 3794)
                        transformation_name = 'wgs84_to_epsg_3794'
                    else:
                        transformed = CoordinateTransformer.transform_polygon_wgs84_to_utm(source_coords)
                        transformation_name = 'wgs84_to_utm'
                else:
                    transformed = CoordinateTransformer.transform_polygon_wgs84_to_utm(source_coords)
                    transformation_name = 'wgs84_to_utm'

                suggestion['suggested_transformation'] = transformation_name
                suggestion['reasoning'] = 'Input coordinates appear to be WGS84 lat/lon. Converted to projected CRS compatible with point cloud bounds.'
                suggestion['transformed_polygon'] = transformed
            except ImportError:
                suggestion['reasoning'] = 'pyproj not installed. Cannot perform coordinate transformation.'
        elif detected_system == 'utm':
            suggestion['reasoning'] = 'Input coordinates already appear to be in UTM or projected system.'
        elif detected_system == 'local':
            suggestion['reasoning'] = 'Input coordinates appear to be in local coordinate system.'
        else:
            suggestion['reasoning'] = 'Could not determine coordinate system. Coordinates may need manual transformation.'

        return suggestion


def transform_user_polygon(polygon: List[List[float]], point_cloud_bounds: Optional[Tuple] = None) -> List[List[float]]:
    """
    Transform user-provided polygon coordinates to match point cloud coordinate system.

    Args:
        polygon: User polygon coordinates [lat, lon] or [x, y]
        point_cloud_bounds: Optional bounds of point cloud to help determine transformation

    Returns:
        Transformed polygon coordinates
    """
    print(f"DEBUG: transform_user_polygon called with polygon: {polygon}")
    print(f"DEBUG: polygon type: {type(polygon)}")
    print(f"DEBUG: polygon length: {len(polygon) if hasattr(polygon, '__len__') else 'no len'}")
    
    suggestion = CoordinateTransformer.suggest_transformation(
        polygon,
        point_cloud_bounds=point_cloud_bounds,
    )

    if suggestion['transformed_polygon']:
        print(f"Coordinate transformation suggestion: {suggestion['reasoning']}")
        return suggestion['transformed_polygon']
    else:
        print(f"No transformation needed: {suggestion['reasoning']}")
        return polygon