"""
Core abstractions for 3D model generation and export.
"""
from abc import ABC, abstractmethod
from typing import Optional, Tuple
import numpy as np
from dataclasses import dataclass


@dataclass
class Mesh:
    """Represents a 3D mesh with vertices, faces, and optional attributes."""
    
    vertices: np.ndarray  # (N, 3) array of vertex positions
    faces: np.ndarray  # (M, 3) array of face indices (triangles)
    colors: Optional[np.ndarray] = None  # (N, 3) RGB colors
    normals: Optional[np.ndarray] = None  # (N, 3) vertex normals
    
    def validate(self) -> None:
        """Validate mesh integrity."""
        if self.vertices.shape[1] != 3:
            raise ValueError("Vertices must have shape (N, 3)")
        
        if self.faces.shape[1] != 3:
            raise ValueError("Faces must have shape (M, 3)")
        
        if np.any(self.faces >= len(self.vertices)):
            raise ValueError("Face indices out of bounds")
        
        if self.colors is not None and self.colors.shape[0] != len(self.vertices):
            raise ValueError("Colors must match number of vertices")
        
        if self.normals is not None and self.normals.shape[0] != len(self.vertices):
            raise ValueError("Normals must match number of vertices")


class ModelGenerator(ABC):
    """Abstract base class for generating 3D models from point clouds."""
    
    @abstractmethod
    def generate(self, points: np.ndarray, **kwargs) -> Mesh:
        """
        Generate mesh from point cloud.
        
        Args:
            points: (N, 3) array of point coordinates
            **kwargs: Algorithm-specific parameters
            
        Returns:
            Generated mesh
        """
        pass


class ModelExporter(ABC):
    """Abstract base class for exporting meshes to various formats."""
    
    @abstractmethod
    def export(self, mesh: Mesh, filepath: str) -> None:
        """
        Export mesh to file.
        
        Args:
            mesh: Mesh to export
            filepath: Output file path
        """
        pass
    
    @abstractmethod
    def supports(self, filename: str) -> bool:
        """Check if exporter supports this file format."""
        pass


class ModelBuilder:
    """Interface for building complex models."""
    
    def __init__(self):
        self.meshes = []
    
    def add_mesh(self, mesh: Mesh) -> 'ModelBuilder':
        """Add mesh to model."""
        mesh.validate()
        self.meshes.append(mesh)
        return self
    
    def combine(self) -> Mesh:
        """Combine all meshes into one."""
        if not self.meshes:
            raise ValueError("No meshes to combine")
        
        if len(self.meshes) == 1:
            return self.meshes[0]
        
        # Combine vertices and faces
        combined_vertices = []
        combined_faces = []
        combined_colors = []
        vertex_offset = 0
        
        has_colors = all(m.colors is not None for m in self.meshes)
        
        for mesh in self.meshes:
            combined_vertices.append(mesh.vertices)
            combined_faces.append(mesh.faces + vertex_offset)
            
            if has_colors and mesh.colors is not None:
                combined_colors.append(mesh.colors)
            
            vertex_offset += len(mesh.vertices)
        
        vertices = np.vstack(combined_vertices)
        faces = np.vstack(combined_faces)
        colors = np.vstack(combined_colors) if has_colors else None
        
        return Mesh(vertices, faces, colors)
