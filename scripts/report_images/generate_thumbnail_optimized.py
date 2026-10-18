"""
Equirectangular -> Perspective View (OpenCV backend)

generate_thumbnail(input_path, output_path, yaw, pitch, hfov, width, height)
renders a rectilinear view from a 360 panorama with one vectorized cv2.remap.
Used by extract_milepost_gui.py when the "opencv" backend is selected.

Requires numpy, opencv-python and scipy (opencv is not in the ArcGIS Pro base env).
"""

import numpy as np
import cv2
from scipy.spatial.transform import Rotation as R

def generate_thumbnail(input_path, output_path, yaw, pitch, hfov, width, height):
    # --- 1) Load & prep ------------------------------------------------------
    img = cv2.imread(str(input_path))
    if img is None:
        raise IOError(f"Could not read image: {input_path}")
    H_in, W_in = img.shape[:2]

    # focal length (same in x/y)
    f = width / (2 * np.tan(0.5 * np.deg2rad(hfov)))

    # --- 2) Build a grid of camera‐space direction vectors ---------------
    # indices: i = row [0..height), j = col [0..width)
    i_coords, j_coords = np.indices((height, width), dtype=np.float32)

    # directions[...,0] = (pixel_row - height/2) / f
    # directions[...,1] = (pixel_col - width/2 ) / f
    # directions[...,2] = 1
    dirs = np.empty((height, width, 3), dtype=np.float32)
    dirs[..., 0] = (i_coords - height * 0.5) / f
    dirs[..., 1] = (j_coords - width  * 0.5) / f
    dirs[..., 2] = 1.0

    # --- 3) Compute the exact same composite rotation ---------------------
    # original did: rot_lat = R.from_rotvec([0,1,0] * (-pitch_rad))
    #               rot_lon = R.from_rotvec([1,0,0] * ( yaw_rad))
    #               dirs_rot = rot_lon.apply(rot_lat.apply(dirs_flat))
    pitch_rad    = np.deg2rad(pitch)
    yaw_rad      = np.deg2rad(yaw)
    rot_lat      = R.from_rotvec(np.array([0.0, -pitch_rad, 0.0]))
    rot_lon      = R.from_rotvec(np.array([ yaw_rad, 0.0,       0.0]))
    # combine into one matrix
    M = rot_lon.as_matrix() @ rot_lat.as_matrix()  # = R_lon · R_lat

    # apply in one batched dot
    dirs_flat     = dirs.reshape(-1, 3)
    dirs_rot_flat = dirs_flat.dot(M.T)
    dirs_rot      = dirs_rot_flat.reshape(height, width, 3)

    # --- 4) Spherical coords (exact same formula) -------------------------
    X = dirs_rot[..., 0]
    Y = dirs_rot[..., 1]
    Z = dirs_rot[..., 2]

    lat = np.arctan2(X, np.sqrt(Z*Z + Y*Y))  # latitude
    lon = np.arctan2(Z, Y)                  # longitude

    # --- 5) Map into equirectangular pixels (same as pixel_coord_from_spherical)
    map_y = (lat + np.pi*0.5) / np.pi      * (H_in - 1)  # row indices
    map_x = (lon + np.pi)        / (2*np.pi) * (W_in - 1)  # col indices

    # --- 6) Remap & flip -------------------------------------------------
    out = cv2.remap(img,
                    map_x.astype(np.float32),
                    map_y.astype(np.float32),
                    interpolation=cv2.INTER_LINEAR)
    out = cv2.flip(out, 1)
    cv2.imwrite(str(output_path), out)
