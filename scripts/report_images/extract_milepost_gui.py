"""
Extract Report Images from 360 Panoramas

Small tkinter GUI that cuts flat perspective views (default 90° HFOV, 4096x1743)
out of equirectangular 360 panoramas for valuation reports. Select images by
milepost (parsed from the filename after a location prefix, e.g. FML12.345),
every Nth image, or all images in a folder.

Backends:
    ffmpeg  - v360 filter (recommended; requires ffmpeg on PATH)
    opencv  - generate_thumbnail_optimized.py (needs numpy, opencv-python, scipy)

Usage:
    python scripts/report_images/extract_milepost_gui.py

Moved here 2026-10-18 from the never-committed E:\\DevProjects\\rmi-360-report-image.
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import re
import subprocess
from pathlib import Path
from generate_thumbnail_optimized import generate_thumbnail


def extract_milepost(filename, prefix):
    match = re.search(fr"{prefix}(\d+\.\d+)", filename)
    return float(match.group(1)) if match else None

class MilepostExtractorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("360° Image Extractor")

        self.input_folder = tk.StringVar()
        self.output_folder = tk.StringVar()
        self.prefix = tk.StringVar(value="FML")
        self.hfov = tk.StringVar(value="90")
        self.resolution = tk.StringVar(value="4096x1743")
        self.yaw = tk.StringVar(value="8")
        self.backend = tk.StringVar(value="ffmpeg")
        self.mode = tk.StringVar(value="all")  # Mode: "milepost", "all", or "every_nth"
        self.nth_value = tk.StringVar(value="10")

        self._build_gui()

    def _build_gui(self):
        frame = tk.Frame(self.root, padx=10, pady=10)
        frame.pack()

        # Input/output folders
        tk.Label(frame, text="Input Folder:").grid(row=0, column=0, sticky="e")
        tk.Entry(frame, textvariable=self.input_folder, width=40).grid(row=0, column=1)
        tk.Button(frame, text="Browse", command=self.browse_input).grid(row=0, column=2)

        tk.Label(frame, text="Output Folder:").grid(row=1, column=0, sticky="e")
        tk.Entry(frame, textvariable=self.output_folder, width=40).grid(row=1, column=1)
        tk.Button(frame, text="Browse", command=self.browse_output).grid(row=1, column=2)

        # Processing Mode
        tk.Label(frame, text="Processing Mode:").grid(row=2, column=0, sticky="ne", pady=5)
        mode_frame = tk.Frame(frame)
        mode_frame.grid(row=2, column=1, columnspan=3, sticky="w")
        tk.Radiobutton(mode_frame, text="All Images", variable=self.mode, value="all", 
                      command=self.toggle_mode_fields).pack(anchor="w")
        tk.Radiobutton(mode_frame, text="Every Nth Image", variable=self.mode, value="every_nth",
                      command=self.toggle_mode_fields).pack(anchor="w")
        tk.Radiobutton(mode_frame, text="By Milepost", variable=self.mode, value="milepost",
                      command=self.toggle_mode_fields).pack(anchor="w")

        # Nth value (for every_nth mode)
        tk.Label(frame, text="Process Every:").grid(row=3, column=0, sticky="e")
        self.nth_label = tk.Label(frame, text="Process Every:")
        self.nth_label.grid(row=3, column=0, sticky="e")
        nth_entry_frame = tk.Frame(frame)
        nth_entry_frame.grid(row=3, column=1, sticky="w")
        self.nth_entry = tk.Entry(nth_entry_frame, textvariable=self.nth_value, width=10)
        self.nth_entry.pack(side="left")
        tk.Label(nth_entry_frame, text=" images").pack(side="left")

        # Prefix (for milepost mode)
        self.prefix_label = tk.Label(frame, text="Location Prefix:")
        self.prefix_label.grid(row=4, column=0, sticky="e")
        self.prefix_entry = tk.Entry(frame, textvariable=self.prefix)
        self.prefix_entry.grid(row=4, column=1, sticky="w")

        # Milepost list (for milepost mode)
        self.milepost_label = tk.Label(frame, text="Target Mileposts\n(comma-separated):")
        self.milepost_label.grid(row=5, column=0, sticky="ne")
        self.milepost_entry = tk.Text(frame, height=3, width=30, wrap="word")
        self.milepost_entry.grid(row=5, column=1, columnspan=3, sticky="w")

        # Backend selection
        tk.Label(frame, text="Projection Backend:").grid(row=6, column=0, sticky="e")
        backend_frame = tk.Frame(frame)
        backend_frame.grid(row=6, column=1, columnspan=3, sticky="w")
        tk.OptionMenu(backend_frame, self.backend, "ffmpeg", "opencv").pack(side="left")
        backend_info = tk.Label(backend_frame, text="ℹ️", fg="blue", cursor="hand2")
        backend_info.pack(side="left", padx=5)
        backend_info.bind("<Button-1>", lambda e: messagebox.showinfo(
            "Backend Comparison",
            "FFmpeg (Recommended):\n"
            "• Faster processing\n"
            "• Higher quality output\n"
            "• Requires ffmpeg installed\n\n"
            "OpenCV:\n"
            "• Pure Python (no external tools)\n"
            "• Slightly slower\n"
            "• Good for portability"
        ))

        # FOV, resolution, yaw
        tk.Label(frame, text="Horizontal FOV (deg):").grid(row=7, column=0, sticky="e")
        tk.Entry(frame, textvariable=self.hfov, width=10).grid(row=7, column=1, sticky="w")

        tk.Label(frame, text="Output Resolution:").grid(row=8, column=0, sticky="e")
        tk.OptionMenu(frame, self.resolution, "1920x817", "2560x1089", "3840x1632", "4096x1743").grid(row=8, column=1, sticky="w")

        tk.Label(frame, text="Yaw Offset (deg):").grid(row=9, column=0, sticky="e")
        tk.Entry(frame, textvariable=self.yaw, width=10).grid(row=9, column=1, sticky="w")

        # Run
        tk.Button(frame, text="Run Extraction", command=self.run_extraction).grid(row=10, column=0, columnspan=4, pady=10)

        # Initialize field visibility
        self.toggle_mode_fields()

    def toggle_mode_fields(self):
        """Show/hide fields based on selected mode"""
        mode = self.mode.get()
        
        if mode == "every_nth":
            # Show nth fields, hide milepost fields
            self.nth_label.grid()
            self.nth_entry.master.grid()
            self.prefix_label.grid_remove()
            self.prefix_entry.grid_remove()
            self.milepost_label.grid_remove()
            self.milepost_entry.grid_remove()
        elif mode == "milepost":
            # Show milepost fields, hide nth fields
            self.nth_label.grid_remove()
            self.nth_entry.master.grid_remove()
            self.prefix_label.grid()
            self.prefix_entry.grid()
            self.milepost_label.grid()
            self.milepost_entry.grid()
        else:  # "all"
            # Hide both
            self.nth_label.grid_remove()
            self.nth_entry.master.grid_remove()
            self.prefix_label.grid_remove()
            self.prefix_entry.grid_remove()
            self.milepost_label.grid_remove()
            self.milepost_entry.grid_remove()

    def browse_input(self):
        folder = filedialog.askdirectory()
        if folder:
            self.input_folder.set(folder)

    def browse_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_folder.set(folder)

    def run_extraction(self):
        try:
            input_dir = Path(self.input_folder.get())
            output_dir = Path(self.output_folder.get())
            hfov = float(self.hfov.get())
            yaw = float(self.yaw.get())
            v_fov = round(hfov / 2.35, 2)
            width, height = map(int, self.resolution.get().split("x"))
            backend = self.backend.get()
            mode = self.mode.get()

            # Get all images from input folder
            all_images = sorted(input_dir.glob("*.jpg"))
            
            if not all_images:
                messagebox.showwarning("No Images", "No .jpg images found in the input folder.")
                return

            # Determine which images to process based on mode
            images_to_process = []
            
            if mode == "all":
                # Process all images
                for image_path in all_images:
                    images_to_process.append((image_path, None))
                    
            elif mode == "every_nth":
                # Process every nth image
                nth = int(self.nth_value.get())
                for i, image_path in enumerate(all_images):
                    if i % nth == 0:
                        images_to_process.append((image_path, None))
                        
            elif mode == "milepost":
                # Process by milepost (original logic)
                prefix = self.prefix.get()
                milepost_list = [float(x.strip()) for x in self.milepost_entry.get("1.0", "end").split(",") if x.strip()]
                
                # Build image map with mileposts
                image_map = []
                for img in all_images:
                    mp = extract_milepost(img.name, prefix)
                    if mp is not None:
                        image_map.append((mp, img))
                image_map.sort()
                
                # Match target mileposts
                for target in milepost_list:
                    selected = None
                    for mp, path in reversed(image_map):
                        if mp < target:
                            selected = path
                            break
                    if selected:
                        images_to_process.append((selected, target))

            if not images_to_process:
                messagebox.showwarning("No Images", "No images selected for processing.")
                return

            processed_count = 0
            for image_path, milepost in images_to_process:
                # Generate output filename
                if milepost is not None:
                    output_file = output_dir / f"{image_path.stem}_mp{milepost:.3f}_rect.jpg"
                else:
                    output_file = output_dir / f"{image_path.stem}_rect.jpg"

                if backend == "ffmpeg":
                    cmd = [
                        "ffmpeg", "-y", "-i", str(image_path),
                        "-vf", f"v360=input=equirect:output=rectilinear:yaw={yaw}:pitch=0:roll=0:h_fov={hfov}:v_fov={v_fov},scale={width}:{height}",
                        "-frames:v", "1", "-q:v", "2", str(output_file)
                    ]
                    subprocess.run(cmd, check=True)

                elif backend == "opencv":
                    generate_thumbnail(
                        input_path=image_path,
                        output_path=output_file,
                        yaw=(yaw - 90) % 360,
                        pitch=0,
                        hfov=hfov,
                        width=width,
                        height=height
                    )
                else:
                    raise ValueError(f"Unknown backend: {backend}")

                processed_count += 1

            messagebox.showinfo("Done", f"Processed {processed_count} images using {backend} backend.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

# Run the app
if __name__ == "__main__":
    root = tk.Tk()
    app = MilepostExtractorApp(root)
    root.mainloop()
