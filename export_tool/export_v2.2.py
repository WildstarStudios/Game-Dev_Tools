bl_info = {
    "name": "Advanced GLB Auto-Exporter",
    "author": "Your Name",
    "version": (2, 2),
    "blender": (4, 4, 0),
    "location": "View3D > Sidebar > GLB Export",
    "description": "Advanced GLB export with tracking and cleanup system",
    "category": "Import-Export",
}

import bpy
import os
import re
import json
import datetime
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.app.handlers import persistent
import mathutils

class ADVANCED_GLB_OT_export(bpy.types.Operator):
    bl_idname = "export.advanced_glb"
    bl_label = "Export GLB"
    bl_description = "Export GLB using current settings"
    bl_options = {'REGISTER'}

    def execute(self, context):
        result = export_glb(context)
        if result == {'FINISHED'}:
            scene_props = context.scene.advanced_glb_props
            if scene_props.export_scope == 'SCENE':
                self.report({'INFO'}, f"Exported scene to {scene_props.export_path}")
            else:
                self.report({'INFO'}, f"Exported {scene_props.export_scope.lower()} to {scene_props.export_path}")
        return result

class ADVANCED_GLB_OT_delete_track_file(bpy.types.Operator):
    bl_idname = "advanced_glb.delete_track_file"
    bl_label = "Delete Track File"
    bl_description = "Delete the export tracking file for this blend file"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        track_file_path = get_track_file_path()
        if os.path.exists(track_file_path):
            os.remove(track_file_path)
            self.report({'INFO'}, f"Deleted track file: {os.path.basename(track_file_path)}")
        else:
            self.report({'WARNING'}, "No track file found")
        return {'FINISHED'}

class ADVANCED_GLB_OT_execute_order_66(bpy.types.Operator):
    bl_idname = "advanced_glb.execute_order_66"
    bl_label = "Execute Order 66"
    bl_description = "Delete orphaned GLB files based on tracking data"
    bl_options = {'REGISTER'}
    
    confirm: BoolProperty(default=False)
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="This will delete orphaned GLB files.", icon='ERROR')
        layout.label(text="This action cannot be undone!")
        
        # Show what will be deleted
        orphans = find_orphaned_files()
        if orphans:
            layout.label(text="Files to be deleted:")
            box = layout.box()
            for orphan in orphans[:10]:  # Show first 10
                box.label(text=f"• {os.path.basename(orphan)}")
            if len(orphans) > 10:
                box.label(text=f"... and {len(orphans) - 10} more")
        else:
            layout.label(text="No orphaned files found.", icon='INFO')
    
    def execute(self, context):
        if not self.confirm:
            self.report({'WARNING'}, "Operation cancelled")
            return {'CANCELLED'}
            
        deleted_files = cleanup_orphaned_files()
        if deleted_files:
            self.report({'INFO'}, f"Executed Order 66: Deleted {len(deleted_files)} orphaned files")
        else:
            self.report({'INFO'}, "No orphaned files found to delete")
        return {'FINISHED'}

class ADVANCED_GLB_PT_panel(bpy.types.Panel):
    bl_label = "GLB Auto-Export"
    bl_idname = "VIEW3D_PT_advanced_glb_export"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'GLB Export'

    def draw(self, context):
        layout = self.layout
        scene_props = context.scene.advanced_glb_props
        prefs = context.preferences.addons[__name__].preferences
        
        # === ESSENTIAL SETTINGS ===
        essential_box = layout.box()
        essential_box.label(text="Essential Settings", icon='SETTINGS')
        
        # Export directory
        if not scene_props.export_path:
            essential_box.label(text="⚠️ Set Export Directory First", icon='ERROR')
        row = essential_box.row()
        row.prop(scene_props, "export_path", text="Export To")
        
        # Export type with clear icons
        essential_box.label(text="Export As:")
        row = essential_box.row()
        row.prop(scene_props, "export_scope", expand=True)
        
        # Scope-specific settings
        if scene_props.export_scope == 'SCENE':
            essential_box.prop(scene_props, "scene_export_filename", text="Filename")
            if scene_props.export_path:
                scene_clean, scene_modifiers = parse_modifiers(scene_props.scene_export_filename)
                final_path = get_final_export_path(scene_props.export_path, scene_modifiers.get('dir'), scene_clean, 'SCENE')
                essential_box.label(text=f"→ {os.path.basename(final_path)}", icon='FILE_BLEND')
                if scene_modifiers.get('dir'):
                    essential_box.label(text=f"📁 Directory: {scene_modifiers['dir']}", icon='FILE_FOLDER')
        
        elif scene_props.export_scope == 'COLLECTION':
            if scene_props.export_path:
                essential_box.label(text="→ Each collection as separate .glb", icon='FILE_BLEND')
                essential_box.label(text="  Naming: {collection_name}.glb")
        
        elif scene_props.export_scope == 'OBJECT':
            if scene_props.export_path:
                essential_box.label(text="→ Each object as separate .glb", icon='FILE_BLEND')
                essential_box.label(text="  Naming: {object_name}.glb")
        
        # Quick summary
        if scene_props.export_path:
            summary_lines = get_quick_summary(scene_props, prefs)
            for line in summary_lines:
                essential_box.label(text=line)
        
        # Export Button - Always visible but disabled if no path
        button_row = essential_box.row()
        button_row.operator("export.advanced_glb", icon='EXPORT', text="Export Now")
        if not scene_props.export_path:
            button_row.enabled = False
            essential_box.label(text="Set export directory to enable export", icon='ERROR')
        
        # === DIRECTORY MODIFIER INFO ===
        if scene_props.export_path:
            dir_box = layout.box()
            dir_box.label(text="Directory Modifiers", icon='FILE_FOLDER')
            dir_box.label(text="Use -dir:path in names to organize exports")
            dir_box.label(text="Examples: 'sword -dir:weapons' or 'enemy -dir:characters'")
            
            # Show examples based on current scope
            if scene_props.export_scope == 'SCENE':
                dir_box.label(text="Scene: 'scene_name -dir:levels'")
            elif scene_props.export_scope == 'COLLECTION':
                dir_box.label(text="Collections: Collection's -dir: used")
            elif scene_props.export_scope == 'OBJECT':
                dir_box.label(text="Objects: Collection's -dir: > Object's -dir:")
        
        # === ADVANCED SETTINGS (Collapsible) ===
        advanced_box = layout.box()
        row = advanced_box.row()
        row.prop(prefs, "show_advanced_settings", text="Advanced Settings", icon='TRIA_DOWN' if prefs.show_advanced_settings else 'TRIA_RIGHT', emboss=False)
        
        if prefs.show_advanced_settings:
            # Auto-export
            auto_row = advanced_box.row()
            auto_row.prop(scene_props, "auto_export_on_save", text="Auto-Export on Save")
            if not scene_props.export_path:
                auto_row.enabled = False
                advanced_box.label(text="Set export directory to enable auto-export", icon='CANCEL')
            
            # Origin handling (disabled for scene export)
            origin_row = advanced_box.row()
            origin_row.label(text="Local Origins:")
            origin_row.prop(prefs, "export_individual_origins", text="Enabled")
            
            if scene_props.export_scope == 'SCENE':
                origin_row.enabled = False
                advanced_box.label(text="Local origins not available for scene export", icon='INFO')
            else:
                advanced_box.label(text="• Objects/collections export at 3D cursor", icon='DOT')
                advanced_box.label(text="• Original positions preserved after export", icon='DOT')
            
            # Modifiers
            advanced_box.prop(prefs, "apply_modifiers", text="Apply Modifiers Before Export")
            
            # Detailed view
            advanced_box.prop(prefs, "show_detailed_list", text="Show Detailed Object List")
            if prefs.show_detailed_list:
                advanced_box.prop(prefs, "show_hidden_objects", text="Include Hidden Objects in List")
        
        # === FILTERING RULES ===
        if prefs.show_advanced_settings:
            filter_box = layout.box()
            filter_box.label(text="Filtering Rules", icon='FILTER')
            filter_box.label(text="• '-dk' in name: Don't export", icon='X')
            filter_box.label(text="• '-sep' on collection: Export separately", icon='COLLECTION_NEW')
            filter_box.label(text="• '-dir:path' in name: Export to subfolder", icon='FILE_FOLDER')
            filter_box.label(text="• Hidden objects/collections: Don't export", icon='HIDE_ON')
        
        # === DETAILED SUMMARY ===
        if scene_props.export_path and prefs.show_detailed_list:
            summary_box = layout.box()
            summary_box.label(text="Detailed Export Summary", icon='INFO')
            
            summary_lines = get_detailed_summary(scene_props, prefs)
            for line in summary_lines:
                summary_box.label(text=line)

class AdvancedGLBPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    show_advanced_settings: BoolProperty(
        name="Show Advanced Settings",
        default=False,
        description="Show advanced export options"
    )
    
    export_individual_origins: BoolProperty(
        name="Export with Local Origins",
        default=True,
        description="Export each object/collection with its local origin at (0,0,0) by moving to 3D cursor"
    )
    
    apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        default=True,
        description="Apply modifiers before export"
    )
    
    show_detailed_list: BoolProperty(
        name="Show Detailed List",
        default=False,
        description="Display detailed list of objects/collections to be exported"
    )
    
    show_hidden_objects: BoolProperty(
        name="Show Hidden Objects",
        default=False,
        description="Include hidden objects in the detailed list"
    )
    
    # Experimental tracking settings
    enable_export_tracking: BoolProperty(
        name="Enable Export Tracking (Experimental)",
        default=False,
        description="Track exported files to identify orphans. Uses .track files"
    )
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="GLB Export Settings")
        
        # Main settings
        layout.prop(self, "export_individual_origins")
        layout.prop(self, "apply_modifiers")
        layout.prop(self, "show_detailed_list")
        layout.prop(self, "show_hidden_objects")
        layout.prop(self, "show_advanced_settings")
        
        # Experimental tracking section
        layout.separator()
        box = layout.box()
        box.label(text="Experimental Tracking System", icon='EXPERIMENTAL')
        box.prop(self, "enable_export_tracking")
        
        if self.enable_export_tracking:
            box.label(text="Tracks exported files to identify orphans", icon='INFO')
            box.label(text="Creates .track files in export directories", icon='FILE_HIDDEN')
            
            # Track file management buttons
            row = box.row()
            row.operator("advanced_glb.delete_track_file", icon='TRASH')
            
            row = box.row()
            op = row.operator("advanced_glb.execute_order_66", icon='COMMUNITY')
            op.confirm = True

class AdvancedGLBSceneProperties(bpy.types.PropertyGroup):
    export_path: StringProperty(
        name="Export Path",
        subtype='DIR_PATH',
        default="",
        description="Directory path for GLB exports. Each blend file remembers its own path"
    )
    
    auto_export_on_save: BoolProperty(
        name="Auto Export on Save",
        default=False,
        description="Automatically export GLB when saving the Blender file"
    )
    
    export_scope: EnumProperty(
        name="Export Scope",
        items=[
            ('SCENE', "Scene", "Export entire scene as one .glb file"),
            ('COLLECTION', "Collections", "Export each collection as individual .glb files"),
            ('OBJECT', "Objects", "Export each object as individual .glb files"),
        ],
        default='SCENE',
        description="Select how to organize the exported files"
    )
    
    scene_export_filename: StringProperty(
        name="Scene Filename",
        default="scene",
        description="Filename for scene export (without .glb extension)"
    )

# ===== TRACKING SYSTEM =====

def get_track_file_path():
    """Get the path for the track file based on blend file name"""
    if bpy.data.filepath:
        blend_name = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
        return os.path.join(os.path.dirname(bpy.data.filepath), f"{blend_name}.export.track")
    else:
        return os.path.join(os.path.expanduser("~"), "unsaved_export.track")

def load_track_data():
    """Load tracking data from track file"""
    track_file = get_track_file_path()
    if os.path.exists(track_file):
        try:
            with open(track_file, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_track_data(track_data):
    """Save tracking data to track file"""
    track_file = get_track_file_path()
    try:
        with open(track_file, 'w') as f:
            json.dump(track_data, f, indent=2)
        return True
    except:
        return False

def update_track_file(exported_files, export_path):
    """Update track file with current export information"""
    prefs = bpy.context.preferences.addons[__name__].preferences
    if not prefs.enable_export_tracking:
        return
    
    track_data = load_track_data()
    
    # Initialize export path data if not exists
    if export_path not in track_data:
        track_data[export_path] = {}
    
    # Update with current export
    track_data[export_path]['last_export'] = {
        'timestamp': datetime.datetime.now().isoformat(),
        'files': exported_files,
        'blend_file': bpy.data.filepath or "unsaved"
    }
    
    # Keep history of last 10 exports for this path
    if 'history' not in track_data[export_path]:
        track_data[export_path]['history'] = []
    
    track_data[export_path]['history'].append({
        'timestamp': datetime.datetime.now().isoformat(),
        'files': exported_files
    })
    
    # Keep only last 10 history entries
    track_data[export_path]['history'] = track_data[export_path]['history'][-10:]
    
    save_track_data(track_data)

def find_orphaned_files():
    """Find orphaned GLB files based on tracking data"""
    track_data = load_track_data()
    orphans = []
    
    for export_path, path_data in track_data.items():
        if not os.path.exists(export_path):
            continue
            
        if 'last_export' not in path_data:
            continue
        
        # Get files that were exported in the last export
        last_export_files = set(path_data['last_export']['files'])
        
        # Find all GLB files in the export directory and subdirectories
        current_files = set()
        for root, dirs, files in os.walk(export_path):
            for file in files:
                if file.lower().endswith('.glb'):
                    full_path = os.path.join(root, file)
                    current_files.add(full_path)
        
        # Orphans are files that exist but weren't in the last export
        for file_path in current_files:
            if file_path not in last_export_files:
                orphans.append(file_path)
    
    return orphans

def cleanup_orphaned_files():
    """Delete orphaned GLB files and update track file"""
    orphans = find_orphaned_files()
    deleted_files = []
    
    for orphan in orphans:
        try:
            os.remove(orphan)
            deleted_files.append(orphan)
            print(f"🗑️ Deleted orphaned file: {orphan}")
        except Exception as e:
            print(f"❌ Failed to delete {orphan}: {str(e)}")
    
    # Update track file to remove references to deleted files
    track_data = load_track_data()
    for export_path, path_data in track_data.items():
        if 'last_export' in path_data:
            # Remove deleted files from last_export record
            path_data['last_export']['files'] = [
                f for f in path_data['last_export']['files'] 
                if f not in deleted_files and os.path.exists(f)
            ]
        
        if 'history' in path_data:
            # Clean up history entries too
            for history_entry in path_data['history']:
                history_entry['files'] = [
                    f for f in history_entry['files']
                    if f not in deleted_files and os.path.exists(f)
                ]
    
    save_track_data(track_data)
    return deleted_files

# ===== EXISTING FUNCTIONS (from previous code) =====

def parse_modifiers(name):
    """Parse modifiers from name and return clean name + modifiers dict"""
    modifiers = {
        'dir': None,
        'sep': False,
        'dk': False
    }
    
    clean_name = name.strip()
    
    # Extract -dir:path modifier
    dir_match = re.search(r'-dir:([^\s]+)', clean_name)
    if dir_match:
        modifiers['dir'] = dir_match.group(1)
        clean_name = clean_name.replace(dir_match.group(0), '').strip()
    
    # Extract boolean modifiers
    modifiers['sep'] = '-sep' in clean_name
    modifiers['dk'] = '-dk' in clean_name
    
    # Remove boolean modifiers from clean name
    clean_name = re.sub(r'\s+-sep\s*', ' ', clean_name).strip()
    clean_name = re.sub(r'\s+-dk\s*', ' ', clean_name).strip()
    
    # Clean up any extra spaces
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
    
    return clean_name, modifiers

def get_final_export_path(base_path, dir_modifier, clean_name, scope):
    """Get the final export path with directory modifiers applied"""
    if dir_modifier:
        # Sanitize path and create directories
        safe_path = os.path.join(base_path, dir_modifier)
        return os.path.join(safe_path, f"{clean_name}.glb")
    else:
        return os.path.join(base_path, f"{clean_name}.glb")

def ensure_directory_exists(filepath):
    """Ensure the directory for a filepath exists, return created status"""
    directory = os.path.dirname(filepath)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
        return True
    return False

def get_collection_for_object(obj):
    """Get the first collection that contains the object (for directory resolution)"""
    for collection in bpy.data.collections:
        if obj.name in collection.objects:
            return collection
    return None

def resolve_export_directory(obj, collection, export_scope, base_export_path):
    """Resolve the export directory based on scope and modifiers"""
    obj_clean, obj_modifiers = parse_modifiers(obj.name)
    
    if export_scope == 'SCENE':
        scene_props = bpy.context.scene.advanced_glb_props
        scene_clean, scene_modifiers = parse_modifiers(scene_props.scene_export_filename)
        dir_path = scene_modifiers.get('dir')
        if dir_path:
            return os.path.join(base_export_path, dir_path)
        return base_export_path
    
    elif export_scope == 'COLLECTION':
        if collection:
            col_clean, col_modifiers = parse_modifiers(collection.name)
            dir_path = col_modifiers.get('dir')
            if dir_path:
                return os.path.join(base_export_path, dir_path)
        return base_export_path
    
    elif export_scope == 'OBJECT':
        if collection:
            col_clean, col_modifiers = parse_modifiers(collection.name)
            dir_path = col_modifiers.get('dir')
            if dir_path:
                return os.path.join(base_export_path, dir_path)
        
        dir_path = obj_modifiers.get('dir')
        if dir_path:
            return os.path.join(base_export_path, dir_path)
        
        return base_export_path
    
    return base_export_path

def get_quick_summary(scene_props, prefs):
    """Generate quick summary of what will be exported"""
    summary_lines = []
    
    if scene_props.export_scope == 'SCENE':
        objects_to_export = [obj for obj in bpy.data.objects if should_export_object(obj)]
        scene_clean, scene_modifiers = parse_modifiers(scene_props.scene_export_filename)
        
        summary_lines.append(f"📦 Exporting {len(objects_to_export)} objects as single file")
        if scene_modifiers.get('dir'):
            summary_lines.append(f"📁 To: {scene_modifiers['dir']}/")
        
    elif scene_props.export_scope == 'COLLECTION':
        export_roots = find_collection_export_roots(bpy.context.scene.collection)
        object_count = sum(
            len([obj for obj in col.all_objects if should_export_object(obj)])
            for root_col, collections in export_roots.items()
            for col in collections
        )
        
        summary_lines.append(f"📦 Exporting {len(export_roots)} collections")
        summary_lines.append(f"📊 Total objects: {object_count}")
        
        dir_collections = []
        for root_col, collections_in_root in export_roots.items():
            col_clean, col_modifiers = parse_modifiers(root_col.name)
            if col_modifiers.get('dir'):
                dir_collections.append(f"{col_clean} → {col_modifiers['dir']}/")
        
        if dir_collections:
            summary_lines.append("📁 Directories:")
            for dir_info in dir_collections[:3]:
                summary_lines.append(f"  {dir_info}")
            if len(dir_collections) > 3:
                summary_lines.append(f"  ... and {len(dir_collections) - 3} more")
        
        if prefs.export_individual_origins:
            summary_lines.append("📍 Each collection at local origin")
        
    elif scene_props.export_scope == 'OBJECT':
        objects_to_export = [obj for obj in bpy.data.objects if should_export_object(obj)]
        summary_lines.append(f"📦 Exporting {len(objects_to_export)} objects")
        
        dir_objects = []
        for obj in objects_to_export[:5]:
            collection = get_collection_for_object(obj)
            export_dir = resolve_export_directory(obj, collection, 'OBJECT', scene_props.export_path)
            if export_dir != scene_props.export_path:
                obj_clean, obj_modifiers = parse_modifiers(obj.name)
                dir_name = os.path.basename(export_dir)
                dir_objects.append(f"{obj_clean} → {dir_name}/")
        
        if dir_objects:
            summary_lines.append("📁 Directories:")
            for dir_info in dir_objects:
                summary_lines.append(f"  {dir_info}")
            if len(objects_to_export) > 5:
                summary_lines.append(f"  ... and {len(objects_to_export) - 5} more objects")
        
        if prefs.export_individual_origins:
            summary_lines.append("📍 Each object at local origin")
    
    return summary_lines

def get_detailed_summary(scene_props, prefs):
    """Generate detailed summary of what will be exported"""
    summary_lines = []
    
    if scene_props.export_scope == 'SCENE':
        objects_to_export = [obj for obj in bpy.data.objects if should_export_object(obj)]
        scene_clean, scene_modifiers = parse_modifiers(scene_props.scene_export_filename)
        
        summary_lines.append(f"Scene Export: {len(objects_to_export)} objects")
        summary_lines.append(f"File: {scene_clean}.glb")
        if scene_modifiers.get('dir'):
            summary_lines.append(f"Directory: {scene_modifiers['dir']}")
        
        if prefs.show_hidden_objects:
            excluded_objects = [obj for obj in bpy.data.objects if not should_export_object(obj)]
            if excluded_objects:
                summary_lines.append("\nExcluded objects:")
                for obj in excluded_objects:
                    reason = get_object_exclusion_reason(obj)
                    summary_lines.append(f"  • {obj.name} ({reason})")
        
    elif scene_props.export_scope == 'COLLECTION':
        export_roots = find_collection_export_roots(bpy.context.scene.collection)
        summary_lines.append(f"Collection Export: {len(export_roots)} collections")
        
        for root_collection, collections_in_root in export_roots.items():
            col_clean, col_modifiers = parse_modifiers(root_collection.name)
            object_count = sum(len([obj for obj in col.all_objects if should_export_object(obj)]) 
                             for col in collections_in_root)
            
            dir_info = f" → {col_modifiers['dir']}/" if col_modifiers.get('dir') else ""
            summary_lines.append(f"\n• {col_clean}.glb{dir_info}: {object_count} objects")
            
            if len(collections_in_root) > 1:
                collection_list = " + ".join([parse_modifiers(col.name)[0] for col in collections_in_root])
                summary_lines.append(f"  Includes: {collection_list}")
            
            if prefs.show_hidden_objects:
                for col in collections_in_root:
                    objects_in_col = [obj for obj in col.all_objects if should_export_object(obj)]
                    if objects_in_col:
                        summary_lines.append(f"  {parse_modifiers(col.name)[0]}:")
                        for obj in objects_in_col:
                            summary_lines.append(f"    • {obj.name} ({obj.type})")
        
        if prefs.show_hidden_objects:
            excluded_collections = [col for col in bpy.data.collections if not should_export_collection(col)]
            if excluded_collections:
                summary_lines.append("\nExcluded collections:")
                for col in excluded_collections:
                    reason = get_collection_exclusion_reason(col)
                    summary_lines.append(f"  • {col.name} ({reason})")
    
    elif scene_props.export_scope == 'OBJECT':
        objects_to_export = [obj for obj in bpy.data.objects if should_export_object(obj)]
        summary_lines.append(f"Object Export: {len(objects_to_export)} objects")
        
        for obj in objects_to_export:
            collection = get_collection_for_object(obj)
            export_dir = resolve_export_directory(obj, collection, 'OBJECT', scene_props.export_path)
            obj_clean, obj_modifiers = parse_modifiers(obj.name)
            
            dir_info = ""
            if export_dir != scene_props.export_path:
                dir_name = os.path.basename(export_dir)
                dir_info = f" → {dir_name}/"
            
            summary_lines.append(f"• {obj_clean}.glb{dir_info} ({obj.type})")
        
        if prefs.show_hidden_objects:
            excluded_objects = [obj for obj in bpy.data.objects if not should_export_object(obj)]
            if excluded_objects:
                summary_lines.append("\nExcluded objects:")
                for obj in excluded_objects:
                    reason = get_object_exclusion_reason(obj)
                    summary_lines.append(f"  • {obj.name} ({reason})")
    
    return summary_lines

def find_collection_export_roots(scene_collection):
    """Find all collection export roots. ALL collections are exportable unless they have -dk."""
    export_roots = {}
    
    def traverse_collections(collection, current_root=None):
        """Recursively traverse collections to find export roots"""
        clean_name, modifiers = parse_modifiers(collection.name)
        
        if modifiers['dk'] or not should_export_collection(collection):
            return
        
        if modifiers['sep']:
            current_root = collection
            if collection not in export_roots:
                export_roots[collection] = []
        
        if current_root is None:
            current_root = collection
            if collection not in export_roots:
                export_roots[collection] = []
        
        if current_root is not None and collection not in export_roots[current_root]:
            export_roots[current_root].append(collection)
        
        for child_collection in collection.children:
            traverse_collections(child_collection, current_root)
    
    for child_collection in scene_collection.children:
        traverse_collections(child_collection)
    
    return export_roots

def get_object_exclusion_reason(obj):
    """Get reason why an object is excluded from export"""
    clean_name, modifiers = parse_modifiers(obj.name)
    
    reasons = []
    if modifiers['dk']:
        reasons.append("'-dk' modifier")
    if obj.hide_viewport:
        reasons.append("hidden in viewport")
    if obj.hide_render:
        reasons.append("hidden in renders")
    if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'ARMATURE'}:
        reasons.append("non-exportable type")
    return ", ".join(reasons) or "unknown reason"

def get_collection_exclusion_reason(col):
    """Get reason why a collection is excluded from export"""
    clean_name, modifiers = parse_modifiers(col.name)
    
    reasons = []
    if modifiers['dk']:
        reasons.append("'-dk' modifier")
    if col.hide_viewport:
        reasons.append("hidden in viewport")
    if col.hide_render:
        reasons.append("hidden in renders")
    return ", ".join(reasons) or "unknown reason"

def should_export_object(obj):
    """Determine if an object should be exported"""
    clean_name, modifiers = parse_modifiers(obj.name)
    
    if modifiers['dk']:
        return False
    
    if obj.hide_viewport or obj.hide_render:
        return False
    
    if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'ARMATURE'}:
        return False
    
    return True

def should_export_collection(col):
    """Determine if a collection should be exported"""
    clean_name, modifiers = parse_modifiers(col.name)
    
    if modifiers['dk']:
        return False
    
    if col.hide_viewport or col.hide_render:
        return False
    
    return True

def move_to_3d_cursor(obj, cursor_location):
    """Move object to 3D cursor while preserving its local transform"""
    world_matrix = obj.matrix_world.copy()
    offset = cursor_location - world_matrix.to_translation()
    obj.location = obj.location + offset

def restore_original_position(obj, original_matrix):
    """Restore object to its original position"""
    obj.matrix_world = original_matrix

def export_glb(context):
    scene_props = context.scene.advanced_glb_props
    prefs = context.preferences.addons[__name__].preferences
    
    if not scene_props.export_path:
        print("Export failed: No export directory specified")
        return {'CANCELLED'}
    
    if not os.path.exists(scene_props.export_path):
        os.makedirs(scene_props.export_path, exist_ok=True)
    
    original_positions = {}
    cursor_location = bpy.context.scene.cursor.location.copy()
    created_directories = set()
    exported_files = []  # Track all files we export in this session
    
    try:
        if prefs.export_individual_origins and scene_props.export_scope != 'SCENE':
            print("📍 Using local origins - moving objects to 3D cursor...")
            
            if scene_props.export_scope == 'COLLECTION':
                export_roots = find_collection_export_roots(bpy.context.scene.collection)
                for root_collection, collections_in_root in export_roots.items():
                    objects_in_root = []
                    for col in collections_in_root:
                        objects_in_root.extend([obj for obj in col.all_objects if should_export_object(obj)])
                    
                    if objects_in_root:
                        for obj in objects_in_root:
                            original_positions[obj] = obj.matrix_world.copy()
                        
                        for obj in objects_in_root:
                            move_to_3d_cursor(obj, cursor_location)
            
            elif scene_props.export_scope == 'OBJECT':
                for obj in bpy.data.objects:
                    if should_export_object(obj):
                        original_positions[obj] = obj.matrix_world.copy()
                        move_to_3d_cursor(obj, cursor_location)
        
        export_settings = {
            'export_format': 'GLB',
            'export_apply': prefs.apply_modifiers,
            'export_yup': True
        }
        
        if scene_props.export_scope == 'SCENE':
            scene_clean, scene_modifiers = parse_modifiers(scene_props.scene_export_filename)
            export_path = get_final_export_path(scene_props.export_path, scene_modifiers.get('dir'), scene_clean, 'SCENE')
            
            if ensure_directory_exists(export_path):
                print(f"📁 Created directory: {os.path.dirname(export_path)}")
            
            export_settings['filepath'] = export_path
            export_settings['use_selection'] = False
            
            try:
                bpy.ops.object.select_all(action='DESELECT')
                for obj in bpy.data.objects:
                    if should_export_object(obj):
                        obj.select_set(True)
                
                bpy.ops.export_scene.gltf(**export_settings)
                print(f"✅ Exported scene to: {export_path}")
                if scene_modifiers.get('dir'):
                    print(f"📁 Directory modifier: {scene_modifiers['dir']}")
                
                exported_files.append(export_path)
                return {'FINISHED'}
            except Exception as e:
                print(f"❌ Scene export failed: {str(e)}")
                return {'CANCELLED'}
        
        elif scene_props.export_scope == 'COLLECTION':
            export_roots = find_collection_export_roots(bpy.context.scene.collection)
            success_count = 0
            
            for root_collection, collections_in_root in export_roots.items():
                col_clean, col_modifiers = parse_modifiers(root_collection.name)
                export_path = get_final_export_path(scene_props.export_path, col_modifiers.get('dir'), col_clean, 'COLLECTION')
                
                if ensure_directory_exists(export_path):
                    dir_created = os.path.dirname(export_path)
                    if dir_created not in created_directories:
                        print(f"📁 Created directory: {dir_created}")
                        created_directories.add(dir_created)
                
                bpy.ops.object.select_all(action='DESELECT')
                object_count = 0
                
                for col in collections_in_root:
                    for obj in col.all_objects:
                        if should_export_object(obj):
                            obj.select_set(True)
                            object_count += 1
                
                if object_count == 0:
                    print(f"⚠️ Skipping '{col_clean}': No exportable objects")
                    continue
                
                root_settings = export_settings.copy()
                root_settings['filepath'] = export_path
                root_settings['use_selection'] = True
                
                try:
                    bpy.ops.export_scene.gltf(**root_settings)
                    collection_list = ", ".join([parse_modifiers(col.name)[0] for col in collections_in_root])
                    print(f"✅ Exported '{col_clean}' to: {export_path}")
                    if col_modifiers.get('dir'):
                        print(f"📁 Directory modifier: {col_modifiers['dir']}")
                    print(f"   Contains {object_count} objects from: {collection_list}")
                    success_count += 1
                    
                    exported_files.append(export_path)
                except Exception as e:
                    print(f"❌ Collection export failed for '{col_clean}': {str(e)}")
            
            return {'FINISHED'} if success_count > 0 else {'CANCELLED'}
        
        elif scene_props.export_scope == 'OBJECT':
            success_count = 0
            
            for obj in bpy.data.objects:
                if not should_export_object(obj):
                    continue
                
                collection = get_collection_for_object(obj)
                obj_clean, obj_modifiers = parse_modifiers(obj.name)
                export_dir = resolve_export_directory(obj, collection, 'OBJECT', scene_props.export_path)
                export_path = os.path.join(export_dir, f"{obj_clean}.glb")
                
                if ensure_directory_exists(export_path):
                    dir_created = os.path.dirname(export_path)
                    if dir_created not in created_directories:
                        print(f"📁 Created directory: {dir_created}")
                        created_directories.add(dir_created)
                
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                
                object_settings = export_settings.copy()
                object_settings['filepath'] = export_path
                object_settings['use_selection'] = True
                
                try:
                    bpy.ops.export_scene.gltf(**object_settings)
                    print(f"✅ Exported '{obj_clean}' to: {export_path}")
                    
                    if collection:
                        col_clean, col_modifiers = parse_modifiers(collection.name)
                        if col_modifiers.get('dir'):
                            print(f"📁 Using collection's directory: {col_modifiers['dir']}")
                        elif obj_modifiers.get('dir'):
                            print(f"📁 Using object's directory: {obj_modifiers['dir']}")
                    
                    success_count += 1
                    exported_files.append(export_path)
                except Exception as e:
                    print(f"❌ Object export failed for '{obj_clean}': {str(e)}")
            
            return {'FINISHED'} if success_count > 0 else {'CANCELLED'}
        
        return {'CANCELLED'}
    
    finally:
        # Update tracking file if we exported anything
        if exported_files and prefs.enable_export_tracking:
            update_track_file(exported_files, scene_props.export_path)
            print(f"📊 Tracking updated: {len(exported_files)} files recorded")
        
        if original_positions:
            print("📍 Restoring original object positions...")
            for obj, original_matrix in original_positions.items():
                if obj:
                    restore_original_position(obj, original_matrix)

@persistent
def on_save_handler(dummy):
    if not bpy.context.preferences.addons.get(__name__):
        return
    
    scene_props = bpy.context.scene.advanced_glb_props
    if not scene_props.auto_export_on_save:
        return
    
    if not scene_props.export_path:
        print("Auto-export skipped: Export directory not configured")
        return
    
    export_glb(bpy.context)

def register():
    bpy.utils.register_class(ADVANCED_GLB_OT_export)
    bpy.utils.register_class(ADVANCED_GLB_OT_delete_track_file)
    bpy.utils.register_class(ADVANCED_GLB_OT_execute_order_66)
    bpy.utils.register_class(ADVANCED_GLB_PT_panel)
    bpy.utils.register_class(AdvancedGLBPreferences)
    bpy.utils.register_class(AdvancedGLBSceneProperties)
    
    bpy.types.Scene.advanced_glb_props = bpy.props.PointerProperty(type=AdvancedGLBSceneProperties)
    
    if on_save_handler not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(on_save_handler)

def unregister():
    bpy.utils.unregister_class(ADVANCED_GLB_OT_export)
    bpy.utils.unregister_class(ADVANCED_GLB_OT_delete_track_file)
    bpy.utils.unregister_class(ADVANCED_GLB_OT_execute_order_66)
    bpy.utils.unregister_class(ADVANCED_GLB_PT_panel)
    bpy.utils.unregister_class(AdvancedGLBPreferences)
    bpy.utils.unregister_class(AdvancedGLBSceneProperties)
    
    del bpy.types.Scene.advanced_glb_props
    
    if on_save_handler in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(on_save_handler)

if __name__ == "__main__":
    register()