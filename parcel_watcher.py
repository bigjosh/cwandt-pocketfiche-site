#!/usr/bin/env python3
"""
Parcel Directory Watcher

Watches a directory for parcel image changes and triggers incremental builds.
Uses file system events to detect changes and runs builds synchronously.

Usage:
  python parcel_watcher.py --parcels-dir parcels --output-dir docs/world
"""

import argparse
import sys
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Import the incremental builder functions directly
import incremental_build


class ParcelChangeHandler(FileSystemEventHandler):
    """Handles file system events for parcel images."""
    
    def __init__(self, parcels_dir: Path, output_dir: Path, debounce_seconds: float = 3.0):
        """
        Initialize the handler.
        
        Args:
            parcels_dir: Directory containing parcel PNG files
            output_dir: Output directory for tiles
            debounce_seconds: Wait time after last change before triggering build
        """
        self.parcels_dir = parcels_dir
        self.output_dir = output_dir
        self.debounce_seconds = debounce_seconds
        self.last_change_time = 0
        self.pending_changes = False
        
    def on_created(self, event):
        """Called when a file is created."""
        if not event.is_directory and event.src_path.endswith('.png'):
            parcel_path = Path(event.src_path)
            parcel_name = parcel_path.stem
            print(f"📝 Detected new parcel: {parcel_name}")
            self._mark_change()
    
    def on_modified(self, event):
        """Called when a file is modified."""
        if not event.is_directory and event.src_path.endswith('.png'):
            parcel_path = Path(event.src_path)
            parcel_name = parcel_path.stem
            print(f"📝 Detected modified parcel: {parcel_name}")
            self._mark_change()
    
    def on_deleted(self, event):
        """Called when a file is deleted."""
        # todo: we need to run --init to deal with a delete for now. 
        if not event.is_directory and event.src_path.endswith('.png'):
            parcel_path = Path(event.src_path)
            parcel_name = parcel_path.stem
            print(f"🗑️  Detected deleted parcel: {parcel_name}")
            self._mark_change()
    
    def _mark_change(self):
        """Mark that a change has occurred."""
        self.last_change_time = time.time()
        self.pending_changes = True
    
    def check_and_build(self):
        """Check if enough time has passed since last change and trigger build."""
        if not self.pending_changes:
            return
        
        time_since_change = time.time() - self.last_change_time
        if time_since_change >= self.debounce_seconds:
            self.pending_changes = False
            self._trigger_build()
    
    def _trigger_build(self):
        """Trigger the incremental build synchronously."""
        print()
        print("=" * 60)
        print("🚀 Triggering incremental build...")
        print("=" * 60)
        
        try:
            # Call incremental_build functions directly (synchronous)
            result = incremental_build.incremental_build(self.parcels_dir, self.output_dir)
            
            if result == 0:
                print()
                print("=" * 60)
                print("✅ Build completed successfully")
                print("=" * 60)
                print()
            else:
                print()
                print("=" * 60)
                print(f"⚠️  Build completed with warnings (exit code: {result})")
                print("=" * 60)
                print()
        except Exception as e:
            print()
            print("=" * 60)
            print(f"❌ Build failed with error: {e}")
            print("=" * 60)
            print()
            import traceback
            traceback.print_exc()


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Watch parcel directory and trigger incremental builds on changes'
    )
    parser.add_argument(
        '--parcels-dir',
        default='parcels',
        help='Directory containing parcel PNG files to watch (default: parcels)'
    )
    parser.add_argument(
        '--output-dir',
        default='docs/world',
        help='Output directory for tile pyramid (default: docs/world)'
    )
    parser.add_argument(
        '--debounce',
        type=float,
        default=3.0,
        help='Seconds to wait after last change before building (default: 3.0)'
    )
    
    args = parser.parse_args()
    
    parcels_dir = Path(args.parcels_dir)
    output_dir = Path(args.output_dir)
    
    # Validate directories
    if not parcels_dir.exists():
        print(f"❌ Error: Parcels directory does not exist: {parcels_dir}")
        return 1
    
    if not output_dir.exists():
        print(f"❌ Error: Output directory does not exist: {output_dir}")
        print(f"   Run 'python incremental_build.py --init' first to initialize.")
        return 1
    
    print("╔════════════════════════════════════════════════════════════╗")
    print("║             Parcel Directory Watcher                       ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    print(f"📁 Watching:  {parcels_dir.absolute()}")
    print(f"📤 Output:    {output_dir.absolute()}")
    print(f"⏱️  Debounce:  {args.debounce} seconds")
    print()
    print("👀 Watching for changes... (Press Ctrl+C to stop)")
    print()
    
    # Set up file system observer
    event_handler = ParcelChangeHandler(parcels_dir, output_dir, args.debounce)
    observer = Observer()
    observer.schedule(event_handler, str(parcels_dir), recursive=False)
    observer.start()
    
    try:
        # Main loop: periodically check if we should trigger a build
        while True:
            time.sleep(0.5)  # Check twice per second
            event_handler.check_and_build()
    except KeyboardInterrupt:
        print()
        print("🛑 Stopping watcher...")
        observer.stop()
    
    observer.join()
    print("✅ Watcher stopped")
    return 0


if __name__ == '__main__':
    sys.exit(main())
