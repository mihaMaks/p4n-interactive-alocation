"""Vehicle catalog with real-world dimensions in meters.

All dimensions (length, width, height) are in meters and correspond to
the mesh coordinate system where 1 unit = 1 meter (EPSG:3794).
"""
from typing import List, Optional

VEHICLE_CATALOG: List[dict] = [
    {
        "id": "small_car",
        "name": "Small Car",
        "description": "Compact car (e.g., VW Polo, Renault Clio)",
        "length": 4.0,
        "width": 1.8,
        "height": 1.5,
        "color": "#3498db",
    },
    {
        "id": "sedan",
        "name": "Sedan",
        "description": "Mid-size sedan (e.g., VW Passat, BMW 3 Series)",
        "length": 4.8,
        "width": 1.8,
        "height": 1.5,
        "color": "#2ecc71",
    },
    {
        "id": "suv",
        "name": "SUV",
        "description": "Sport utility vehicle (e.g., VW Tiguan)",
        "length": 4.5,
        "width": 1.9,
        "height": 1.7,
        "color": "#e67e22",
    },
    {
        "id": "van",
        "name": "Van",
        "description": "Delivery van (e.g., VW Transporter)",
        "length": 5.3,
        "width": 1.9,
        "height": 2.0,
        "color": "#9b59b6",
    },
    {
        "id": "truck",
        "name": "Truck",
        "description": "Medium truck",
        "length": 8.0,
        "width": 2.5,
        "height": 3.5,
        "color": "#e74c3c",
    },
    {
        "id": "bus",
        "name": "Bus",
        "description": "City bus",
        "length": 12.0,
        "width": 2.5,
        "height": 3.2,
        "color": "#f39c12",
    },
    {
        "id": "motorcycle",
        "name": "Motorcycle",
        "description": "Standard motorcycle",
        "length": 2.2,
        "width": 0.8,
        "height": 1.1,
        "color": "#1abc9c",
    },
    {
        "id": "bicycle",
        "name": "Bicycle",
        "description": "Standard bicycle",
        "length": 1.8,
        "width": 0.6,
        "height": 1.0,
        "color": "#34495e",
    },
    {
        "id": "custom",
        "name": "Custom",
        "description": "Enter your own dimensions",
        "length": 4.0,
        "width": 2.0,
        "height": 1.5,
        "color": "#95a5a6",
    },
]


def get_catalog() -> List[dict]:
    """Return the full vehicle catalog."""
    return VEHICLE_CATALOG


def get_vehicle(vehicle_id: str) -> Optional[dict]:
    """Look up a single vehicle by id."""
    for vehicle in VEHICLE_CATALOG:
        if vehicle["id"] == vehicle_id:
            return vehicle
    return None
