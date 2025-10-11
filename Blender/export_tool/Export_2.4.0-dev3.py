bl_info = {
    "name": "Advanced Auto-Exporter",
    "author": "WildStar Studios", 
    "version": (2, 4, 0, "dev 3"),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > Export",
    "description": "Advanced export with proper collection origin handling",
    "category": "Import-Export",
}

import bpy
import os
import re
import json
import datetime
from bpy.props import StringProperty, BoolProperty, EnumProperty, FloatProperty
from bpy.app.handlers import persistent
import mathutils
from mathutils import Vector

# ===== GLOBAL EXPORT STATE =====
class ExportState:
    """Global state to track export status"""
    is_exporting = False

# ===== OPERATORS =====
class ADVANCED_GLB_OT_export(bpy.types.Operator):
    bl_idname = "export.advanced_glb"
    bl_label = "Export"
    bl_description = "Export using current settings"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene_props = context.scene.advanced_glb_props
        
        # Check if already exporting
        if ExportState.is_exporting:
            self.report({'WARNING'}, "Export already in progress. Please wait.")
            return {'CANCELLED'}
        
        # Check for animation warnings
        if scene_props.apply_animations:
            if scene_props.export_format in ['OBJ']:
                self.report({'WARNING'}, f"{scene_props.export_format} format doesn't support animations!")
            else:
                self.report({'INFO'}, f"{scene_props.export_format} format supports animations")
        
        # Synchronous export with locking
        ExportState.is_exporting = True
        try:
            result = export_glb(context)
            if result == {'FINISHED'}:
                if scene_props.export_scope == 'SCENE':
                    self.report({'INFO'}, f"Exported scene to {scene_props.export_path}")
                else:
                    self.report({'INFO'}, f"Exported {scene_props.export_scope.lower()} to {scene_props.export_path}")
            return result
        finally:
            ExportState.is_exporting = False

class ADVANCED_GLB_OT_export_selected(bpy.types.Operator):
    bl_idname = "export.advanced_glb_selected"
    bl_label = "Export Selected"
    bl_description = "Export only the currently selected objects"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene_props = context.scene.advanced_glb_props
        
        # Check if already exporting
        if ExportState.is_exporting:
            self.report({'WARNING'}, "Export already in progress. Please wait.")
            return {'CANCELLED'}
        
        # Get selected items - both objects and collections
        selected_items = get_selected_items(context)
        
        if not selected_items['objects'] and not selected_items['collections']:
            self.report({'WARNING'}, "No objects or collections selected")
            return {'CANCELLED'}
        
        # Check for animation warnings
        if scene_props.apply_animations and scene_props.export_format in ['OBJ']:
            self.report({'WARNING'}, f"{scene_props.export_format} format doesn't support animations!")
        
        # Synchronous export with locking
        ExportState.is_exporting = True
        try:
            result = export_selected(context, selected_items)
            if result == {'FINISHED'}:
                obj_count = len(selected_items['objects'])
                col_count = len(selected_items['collections'])
                self.report({'INFO'}, f"Exported {obj_count} objects, {col_count} collections to {scene_props.export_path}")
            return result
        finally:
            ExportState.is_exporting = False

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
    bl_description = "Delete orphaned files based on tracking data"
    bl_options = {'REGISTER'}
    
    confirm: BoolProperty(default=False)
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="This will delete orphaned files.", icon='ERROR')
        layout.label(text="This action cannot be undone!")
        
        orphans = find_orphaned_files()
        if orphans:
            layout.label(text="Files to be deleted:")
            box = layout.box()
            for orphan in orphans[:10]:
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

class ADVANCED_GLB_OT_validate_sk_modifiers(bpy.types.Operator):
    bl_idname = "advanced_glb.validate_sk_modifiers"
    bl_label = "Validate -sk Modifiers"
    bl_description = "Check for invalid -sk modifier usage in collections"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        invalid_collections = validate_sk_modifiers()
        
        if not invalid_collections:
            self.report({'INFO'}, "All -sk modifiers are valid")
            return {'FINISHED'}
        
        report_lines = []
        for col, issues in invalid_collections.items():
            report_lines.append(f"Collection '{col.name}':")
            for issue in issues:
                report_lines.append(f"  • {issue}")
        
        def draw_report(self, context):
            layout = self.layout
            for line in report_lines:
                layout.label(text=line)
        
        context.window_manager.popup_menu(draw_report, title="Invalid -sk Modifier Usage", icon='ERROR')
        
        self.report({'WARNING'}, f"Found {len(invalid_collections)} collections with invalid -sk usage")
        return {'FINISHED'}

# ===== CLEAN UI PANEL =====
class ADVANCED_GLB_PT_panel(bpy.types.Panel):
    bl_label = "Advanced Auto-Export"
    bl_idname = "VIEW3D_PT_advanced_glb_export"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Export'

    def draw(self, context):
        layout = self.layout
        scene_props = context.scene.advanced_glb_props
        prefs = context.preferences.addons[__name__].preferences
        
        # === VERSION INFO ===
        version_box = layout.box()
        version_box.label(text="🚀 Version 2.4.0 dev3", icon='EXPERIMENTAL')
        
        # === QUICK EXPORT SECTION ===
        quick_box = layout.box()
        
        # Export destination
        row = quick_box.row()
        row.label(text="Export To:", icon='EXPORT')
        row = quick_box.row()
        row.prop(scene_props, "export_path", text="")
        
        if not scene_props.export_path:
            quick_box.label(text="Set export directory first", icon='ERROR')
            return
            
        # Format and Scope in one row
        row = quick_box.row(align=True)
        row.prop(scene_props, "export_format", text="")
        row.prop(scene_props, "export_scope", expand=True, text="Scope")
        
        # Up Axis for all formats
        quick_box.prop(scene_props, "export_up_axis", expand=True)
        
        # Scene filename when in scene mode
        if scene_props.export_scope == 'SCENE':
            row = quick_box.row(align=True)
            row.label(text="Filename:")
            row.prop(scene_props, "scene_export_filename", text="")
        
        # Animation warning
        if scene_props.apply_animations:
            if scene_props.export_format in ['OBJ']:
                quick_box.label(text="⚠️ OBJ doesn't support animations!", icon='ERROR')
            else:
                quick_box.label(text="✓ Format supports animations", icon='CHECKMARK')
        
        # Quick stats
        stats = self.get_quick_stats(scene_props)
        if stats:
            stats_box = quick_box.box()
            for stat in stats:
                stats_box.label(text=stat)
        
        # Export buttons
        button_text = self.get_export_button_text(scene_props)
        
        if ExportState.is_exporting:
            export_row = quick_box.row()
            export_row.enabled = False
            export_row.operator("export.advanced_glb", text="Exporting...", icon='LOADING')
            quick_box.label(text="Export in progress...", icon='TIME')
        else:
            # Main export button
            export_row = quick_box.row()
            export_row.operator("export.advanced_glb", text=button_text, icon='EXPORT')
            
            # Selective export button (only if something is selected)
            selected_items = get_selected_items(context)
            
            if selected_items['objects'] or selected_items['collections']:
                select_row = quick_box.row()
                select_label = self.get_select_export_button_label(selected_items)
                select_row.operator("export.advanced_glb_selected", text=select_label, icon='SELECT_SET')
        
        # === SETTINGS SECTION ===
        settings_box = layout.box()
        settings_box.label(text="Settings", icon='PREFERENCES')
        
        # Main settings in a grid
        grid = settings_box.grid_flow(columns=2, align=True)
        
        grid.prop(prefs, "export_individual_origins", text="Local Origins")
        grid.prop(prefs, "apply_modifiers", text="Apply Modifiers")
        grid.prop(scene_props, "auto_export_on_save", text="Auto-Export")
        grid.prop(scene_props, "apply_animations", text="Apply Animations")
        grid.prop(prefs, "show_detailed_list", text="Show Details")
        
        if prefs.show_detailed_list:
            grid.prop(prefs, "show_hidden_objects", text="Show Hidden")
        
        # === MODIFIERS INFO ===
        mod_box = layout.box()
        mod_box.label(text="Name Modifiers", icon='SYNTAX_OFF')
        
        mod_grid = mod_box.grid_flow(columns=2, align=True)
        mod_grid.label(text="• -dir:folder → Organize in subfolder")
        mod_grid.label(text="• -sep → Export collection separately")
        mod_grid.label(text="• -dk → Don't export this item")  
        mod_grid.label(text="• -sk → Skip collection (ignore)")
        mod_grid.label(text="• -anim → Include animations")
        mod_grid.label(text="• Hidden items → Not exported")
        
        # Validation button
        row = mod_box.row()
        row.operator("advanced_glb.validate_sk_modifiers", icon='CHECKMARK')
        
        # === TRACKING SYSTEM ===
        if prefs.enable_export_tracking:
            track_box = layout.box()
            track_box.label(text="File Tracking", icon='FILE_ARCHIVE')
            
            track_box.prop(prefs, "track_file_location", expand=True)
            
            row = track_box.row(align=True)
            row.operator("advanced_glb.delete_track_file", text="Delete Track File")
            row.operator("advanced_glb.execute_order_66", text="Clean Orphans")
        
        # === DETAILED VIEW ===
        if prefs.show_detailed_list:
            detail_box = layout.box()
            detail_box.label(text="Export Details", icon='INFO')
            
            details = self.get_detailed_export_info(scene_props, prefs)
            for detail in details:
                detail_box.label(text=detail)

    def get_quick_stats(self, scene_props):
        """Get quick statistics about what will be exported"""
        if not scene_props.export_path:
            return []
            
        stats = []
        extension = get_extension(scene_props.export_format)
        
        if ExportState.is_exporting:
            stats.append("🔄 Export in progress...")
            return stats
            
        if scene_props.export_scope == 'SCENE':
            objects = [obj for obj in bpy.data.objects if should_export_object(obj)]
            stats.append(f"📦 Scene: {len(objects)} objects")
            
        elif scene_props.export_scope == 'COLLECTION':
            roots = find_collection_export_roots(bpy.context.scene.collection)
            object_count = sum(
                len([obj for obj in col.all_objects if should_export_object(obj)])
                for root_col, collections in roots.items()
                for col in collections
            )
            stats.append(f"📦 Collections: {len(roots)}")
            stats.append(f"📊 Objects: {object_count}")
            
        elif scene_props.export_scope == 'OBJECT':
            objects = [obj for obj in bpy.data.objects if should_export_object(obj)]
            stats.append(f"📦 Objects: {len(objects)}")
            
        return stats

    def get_export_button_text(self, scene_props):
        """Get text for the export button"""
        if ExportState.is_exporting:
            return "Exporting..."
        if scene_props.export_scope == 'SCENE':
            clean_name, _ = parse_modifiers(scene_props.scene_export_filename)
            return f"Export {clean_name}"
        else:
            return f"Export {scene_props.export_scope.title()}s"

    def get_select_export_button_label(self, selected_items):
        """Get label for selective export button"""
        obj_count = len(selected_items['objects'])
        col_count = len(selected_items['collections'])
        
        if obj_count > 0 and col_count > 0:
            return f"Export Selected ({obj_count} obj, {col_count} col)"
        elif obj_count > 0:
            return f"Export Selected ({obj_count} objects)"
        elif col_count > 0:
            return f"Export Selected ({col_count} collections)"
        else:
            return "Export Selected"

    def get_detailed_export_info(self, scene_props, prefs):
        """Get detailed export information"""
        details = []
        extension = get_extension(scene_props.export_format)
        
        if ExportState.is_exporting:
            details.append("Export in progress...")
            return details
            
        if scene_props.export_scope == 'SCENE':
            objects = [obj for obj in bpy.data.objects if should_export_object(obj)]
            clean_name, modifiers = parse_modifiers(scene_props.scene_export_filename)
            
            details.append(f"File: {clean_name}{extension}")
            if modifiers.get('dir'):
                details.append(f"Directory: {modifiers['dir']}")
            details.append(f"Objects: {len(objects)}")
            
            if prefs.show_hidden_objects:
                excluded = [obj for obj in bpy.data.objects if not should_export_object(obj)]
                if excluded:
                    details.append("Excluded:")
                    for obj in excluded[:5]:
                        details.append(f"  • {obj.name}")

        elif scene_props.export_scope == 'COLLECTION':
            roots = find_collection_export_roots(bpy.context.scene.collection)
            details.append(f"Exporting {len(roots)} collections:")
            
            for root_col, collections in roots.items():
                clean_name, modifiers = parse_modifiers(root_col.name)
                obj_count = sum(len([obj for obj in col.all_objects if should_export_object(obj)]) for col in collections)
                dir_info = f" → {modifiers['dir']}" if modifiers.get('dir') else ""
                details.append(f"• {clean_name}{dir_info}: {obj_count} objects")

        elif scene_props.export_scope == 'OBJECT':
            objects = [obj for obj in bpy.data.objects if should_export_object(obj)]
            details.append(f"Exporting {len(objects)} objects:")
            
            for obj in objects[:10]:
                clean_name, modifiers = parse_modifiers(obj.name)
                collection = get_collection_for_object(obj)
                dir_info = ""
                if collection:
                    _, col_modifiers = parse_modifiers(collection.name)
                    if col_modifiers.get('dir'):
                        dir_info = f" → {col_modifiers['dir']}"
                details.append(f"• {clean_name}{dir_info}")
                
            if len(objects) > 10:
                details.append(f"... and {len(objects) - 10} more")
                
        return details

# ===== PREFERENCES =====
class AdvancedGLBPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

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
    
    enable_export_tracking: BoolProperty(
        name="Enable Export Tracking",
        default=True,
        description="Track exported files to identify orphans. Uses .track files"
    )
    
    track_file_location: EnumProperty(
        name="Track File Location",
        items=[
            ('BLEND', "With Blend File", "Store track file with the .blend file"),
            ('EXPORT', "In Export Directory", "Store track file in the export directory")
        ],
        default='BLEND',
        description="Where to store the export tracking file"
    )

    def draw(self, context):
        layout = self.layout
        
        # Main settings
        main_box = layout.box()
        main_box.label(text="Export Behavior", icon='EXPORT')
        main_box.prop(self, "export_individual_origins")
        main_box.prop(self, "apply_modifiers")
        
        # Display settings
        display_box = layout.box()
        display_box.label(text="Display Options", icon='VIEW3D')
        display_box.prop(self, "show_detailed_list")
        display_box.prop(self, "show_hidden_objects")
        
        # Tracking settings
        track_box = layout.box()
        track_box.label(text="File Tracking", icon='FILE_ARCHIVE')
        track_box.prop(self, "enable_export_tracking")
        
        if self.enable_export_tracking:
            track_box.prop(self, "track_file_location")
            
            # Management buttons
            row = track_box.row()
            row.operator("advanced_glb.delete_track_file", icon='TRASH')
            row.operator("advanced_glb.execute_order_66", icon='COMMUNITY')

# ===== PROPERTIES =====
class AdvancedGLBSceneProperties(bpy.types.PropertyGroup):
    export_path: StringProperty(
        name="Export Path",
        subtype='DIR_PATH',
        default="",
        description="Directory path for exports. Each blend file remembers its own path"
    )
    
    auto_export_on_save: BoolProperty(
        name="Auto Export on Save",
        default=True,
        description="Automatically export when saving the Blender file"
    )
    
    export_scope: EnumProperty(
        name="Export Scope",
        items=[
            ('SCENE', "Scene", "Export entire scene as one file"),
            ('COLLECTION', "Collections", "Export each collection as individual files"),
            ('OBJECT', "Objects", "Export each object as individual files"),
        ],
        default='SCENE',
        description="Select how to organize the exported files"
    )
    
    scene_export_filename: StringProperty(
        name="Scene Filename",
        default="scene",
        description="Filename for scene export (without extension)"
    )
    
    export_format: EnumProperty(
        name="Export Format",
        items=[
            ('GLB', "GLB", "GLB Binary (.glb)"),
            ('GLTF', "GLTF", "GLTF Separate (.gltf + .bin + textures)"),
            ('OBJ', "OBJ", "Wavefront OBJ (.obj)"),
            ('FBX', "FBX", "FBX (.fbx)"),
        ],
        default='GLB',
        description="Export file format"
    )
    
    export_up_axis: EnumProperty(
        name="Export Up Axis",
        items=[
            ('Y', "Y Up", "Y is up (standard for most applications)"),
            ('Z', "Z Up", "Z is up (Blender's default)"),
        ],
        default='Y',
        description="Up axis for all exports"
    )
    
    apply_animations: BoolProperty(
        name="Apply Animations",
        default=False,
        description="Include animations in export (if format supports it)"
    )

# ===== UTILITY FUNCTIONS =====
def get_selected_items(context):
    """Get selected objects and collections - FIXED VERSION"""
    selected_objects = context.selected_objects
    selected_collections = []
    
    # NEW: Use context.selected_ids which properly detects collections selected in outliner
    try:
        for item in context.selected_ids:
            if hasattr(item, 'name') and isinstance(item, bpy.types.Collection):
                selected_collections.append(item)
    except Exception as e:
        print(f"Debug: Error with selected_ids: {e}")
        # Fallback to outliner area detection
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'OUTLINER':
                    try:
                        # Get the space data for the outliner area
                        space = area.spaces.active
                        if hasattr(space, 'selected_ids'):
                            for item in space.selected_ids:
                                if hasattr(item, 'name') and isinstance(item, bpy.types.Collection):
                                    if item not in selected_collections:
                                        selected_collections.append(item)
                    except Exception as e:
                        print(f"Debug: Outliner fallback error: {e}")
    
    return {
        'objects': selected_objects,
        'collections': selected_collections
    }

def get_all_objects_from_collection(collection):
    """Get all exportable objects from a collection and its children"""
    objects = []
    
    def traverse_collection(col):
        # Add objects from this collection
        for obj in col.objects:
            if should_export_object(obj):
                objects.append(obj)
        # Traverse child collections
        for child_col in col.children:
            traverse_collection(child_col)
    
    traverse_collection(collection)
    return objects

def get_extension(format_type):
    """Get file extension for format"""
    extensions = {
        'GLB': '.glb',
        'GLTF': '.gltf', 
        'OBJ': '.obj',
        'FBX': '.fbx'
    }
    return extensions.get(format_type, '.glb')

def check_operator_exists(operator_name):
    """Check if an operator exists in Bforartists"""
    try:
        op_class = getattr(bpy.ops, operator_name.split('.')[1])
        return hasattr(op_class, 'poll')
    except:
        return False

def get_available_export_operators():
    """Get available export operators in Bforartists"""
    available_ops = {}
    
    test_operators = {
        'GLB': ['export_scene.gltf'],
        'GLTF': ['export_scene.gltf'],
        'OBJ': ['export_scene.obj', 'export_mesh.obj', 'wm.obj_export'],
        'FBX': ['export_scene.fbx', 'wm.fbx_export']
    }
    
    for format_type, operators in test_operators.items():
        for op in operators:
            if check_operator_exists(op):
                available_ops[format_type] = op
                break
    
    return available_ops

def export_obj_compat(filepath, use_selection=False, apply_modifiers=True):
    """
    Export OBJ files with compatibility for both Blender <4.0 and >=4.0
    """
    try:
        scene_props = bpy.context.scene.advanced_glb_props
        
        if bpy.app.version >= (4, 0, 0):
            export_params = {
                'filepath': filepath,
                'export_selected_objects': use_selection,
                'apply_modifiers': apply_modifiers,
                'export_normals': True,
                'export_uv': True,
                'export_materials': True,
                'export_triangulated_mesh': False,
                'global_scale': 1.0,
                'forward_axis': 'Y',
                'up_axis': scene_props.export_up_axis
            }
            
            bpy.ops.wm.obj_export(**export_params)
            print(f"✅ Exported OBJ (4.0+ method) to: {filepath}")
            return True
            
        else:
            if scene_props.export_up_axis == 'Y':
                axis_forward = '-Z'
                axis_up = 'Y'
            else:
                axis_forward = 'Y' 
                axis_up = 'Z'
            
            export_params = {
                'filepath': filepath,
                'use_selection': use_selection,
                'use_mesh_modifiers': apply_modifiers,
                'use_normals': True,
                'use_uvs': True,
                'use_materials': True,
                'use_triangles': False,
                'use_nurbs': False,
                'use_vertex_groups': False,
                'use_blen_objects': True,
                'group_by_object': False,
                'group_by_material': False,
                'keep_vertex_order': False,
                'global_scale': 1.0,
                'path_mode': 'AUTO',
                'axis_forward': axis_forward,
                'axis_up': axis_up
            }
            
            bpy.ops.export_scene.obj(**export_params)
            print(f"✅ Exported OBJ (legacy method) to: {filepath}")
            return True
            
    except Exception as e:
        print(f"❌ OBJ export failed: {str(e)}")
        return False

def get_collection_center(collection_objects):
    """Calculate the center point of all objects in a collection"""
    if not collection_objects:
        return Vector((0, 0, 0))
    
    total_position = Vector((0, 0, 0))
    valid_objects = 0
    
    for obj in collection_objects:
        if obj and obj.matrix_world:
            total_position += obj.matrix_world.translation
            valid_objects += 1
    
    if valid_objects == 0:
        return Vector((0, 0, 0))
    
    return total_position / valid_objects

def move_collection_to_origin(collection_objects, cursor_location):
    """Move entire collection to cursor while maintaining relative positions"""
    if not collection_objects:
        return {}
    
    original_positions = {}
    for obj in collection_objects:
        if obj:
            original_positions[obj] = obj.matrix_world.copy()
    
    collection_center = get_collection_center(collection_objects)
    offset = cursor_location - collection_center
    
    for obj in collection_objects:
        if obj:
            new_position = obj.matrix_world.translation + offset
            obj.matrix_world.translation = new_position
    
    return original_positions

def restore_collection_positions(original_positions):
    """Restore collection objects to their original positions"""
    for obj, original_matrix in original_positions.items():
        if obj:
            obj.matrix_world = original_matrix

def parse_modifiers(name):
    """Parse modifiers from name and return clean name + modifiers dict"""
    modifiers = {
        'dir': None,
        'sep': False,
        'dk': False,
        'sk': False,
        'anim': False
    }
    
    clean_name = name.strip()
    
    dir_match = re.search(r'\s*-dir:([^\s]+)\s*', clean_name)
    if dir_match:
        modifiers['dir'] = dir_match.group(1).strip()
        clean_name = clean_name.replace(dir_match.group(0), ' ').strip()
    
    if re.search(r'\s*-sep\s*', clean_name):
        modifiers['sep'] = True
        clean_name = re.sub(r'\s*-sep\s*', ' ', clean_name).strip()
    
    if re.search(r'\s*-dk\s*', clean_name):
        modifiers['dk'] = True
        clean_name = re.sub(r'\s*-dk\s*', ' ', clean_name).strip()
    
    if re.search(r'\s*-sk\s*', clean_name):
        modifiers['sk'] = True
        clean_name = re.sub(r'\s*-sk\s*', ' ', clean_name).strip()
    
    if re.search(r'\s*-anim\s*', clean_name):
        modifiers['anim'] = True
        clean_name = re.sub(r'\s*-anim\s*', ' ', clean_name).strip()
    
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
    
    return clean_name, modifiers

def validate_sk_modifiers():
    """
    Validate -sk modifier usage.
    Returns a dict of collections with invalid -sk usage and their issues.
    """
    invalid_collections = {}
    
    def check_collection_sk_usage(collection):
        issues = []
        clean_name, modifiers = parse_modifiers(collection.name)
        
        if not modifiers['sk']:
            return issues
        
        for obj in collection.objects:
            obj_clean, obj_modifiers = parse_modifiers(obj.name)
            if obj_modifiers['anim']:
                issues.append(f"Object '{obj.name}' has -anim modifier but collection is skipped")
        
        for subcol in collection.children:
            sub_issues = check_collection_sk_usage(subcol)
            if sub_issues:
                issues.extend([f"Subcollection '{subcol.name}': {issue}" for issue in sub_issues])
        
        return issues
    
    for collection in bpy.data.collections:
        issues = check_collection_sk_usage(collection)
        if issues:
            invalid_collections[collection] = issues
    
    return invalid_collections

def get_track_file_path():
    """Get the path for the track file based on preferences"""
    prefs = bpy.context.preferences.addons[__name__].preferences
    
    if prefs.track_file_location == 'EXPORT':
        scene_props = bpy.context.scene.advanced_glb_props
        if scene_props.export_path:
            if bpy.data.filepath:
                blend_name = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
            else:
                blend_name = "unsaved"
            return os.path.join(scene_props.export_path, f"{blend_name}.export.track")
        else:
            return get_blend_track_file_path()
    else:
        return get_blend_track_file_path()

def get_blend_track_file_path():
    """Get track file path in blend file directory"""
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
        os.makedirs(os.path.dirname(track_file), exist_ok=True)
        with open(track_file, 'w') as f:
            json.dump(track_data, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ Failed to save track file: {str(e)}")
        return False

def update_track_file(exported_files, export_path):
    """Update track file with current export information"""
    prefs = bpy.context.preferences.addons[__name__].preferences
    if not prefs.enable_export_tracking:
        return
    
    track_data = load_track_data()
    
    export_key = export_path
    
    if export_key not in track_data:
        track_data[export_key] = {}
    
    track_data[export_key]['last_export'] = {
        'timestamp': datetime.datetime.now().isoformat(),
        'files': exported_files,
        'blend_file': bpy.data.filepath or "unsaved",
        'format': bpy.context.scene.advanced_glb_props.export_format
    }
    
    if 'history' not in track_data[export_key]:
        track_data[export_key]['history'] = []
    
    track_data[export_key]['history'].append({
        'timestamp': datetime.datetime.now().isoformat(),
        'files': exported_files,
        'format': bpy.context.scene.advanced_glb_props.export_format
    })
    
    track_data[export_key]['history'] = track_data[export_key]['history'][-10:]
    
    save_track_data(track_data)

def find_orphaned_files():
    """Find orphaned files based on tracking data"""
    track_data = load_track_data()
    orphans = []
    
    for export_path, path_data in track_data.items():
        if not os.path.exists(export_path):
            continue
            
        if 'last_export' not in path_data:
            continue
        
        last_export_files = set(path_data['last_export']['files'])
        
        current_files = set()
        supported_extensions = {'.glb', '.gltf', '.obj', '.fbx', '.bin'}
        
        for root, dirs, files in os.walk(export_path):
            if root.endswith('.export.track'):
                continue
                
            for file in files:
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext in supported_extensions:
                    full_path = os.path.join(root, file)
                    current_files.add(full_path)
        
        all_tracked_files = set()
        for track_export_path, track_path_data in track_data.items():
            if 'last_export' in track_path_data:
                all_tracked_files.update(track_path_data['last_export']['files'])
        
        for file_path in current_files:
            if file_path not in last_export_files and file_path not in all_tracked_files:
                orphans.append(file_path)
    
    return orphans

def cleanup_orphaned_files():
    """Delete orphaned files and update track file"""
    orphans = find_orphaned_files()
    deleted_files = []
    
    for orphan in orphans:
        try:
            base_name = os.path.splitext(orphan)[0]
            parent_dir = os.path.dirname(orphan)
            
            os.remove(orphan)
            deleted_files.append(orphan)
            print(f"🗑️ Deleted orphaned file: {orphan}")
            
            if orphan.endswith('.gltf'):
                bin_file = os.path.join(parent_dir, base_name + '.bin')
                if os.path.exists(bin_file):
                    os.remove(bin_file)
                    deleted_files.append(bin_file)
                    print(f"🗑️ Deleted associated file: {bin_file}")
                
                textures_dir = os.path.join(parent_dir, base_name + '_textures')
                if os.path.exists(textures_dir):
                    import shutil
                    shutil.rmtree(textures_dir)
                    print(f"🗑️ Deleted textures directory: {textures_dir}")
            
        except Exception as e:
            print(f"❌ Failed to delete {orphan}: {str(e)}")
    
    track_data = load_track_data()
    for export_path, path_data in track_data.items():
        if 'last_export' in path_data:
            path_data['last_export']['files'] = [
                f for f in path_data['last_export']['files'] 
                if f not in deleted_files and os.path.exists(f)
            ]
        
        if 'history' in path_data:
            for history_entry in path_data['history']:
                history_entry['files'] = [
                    f for f in history_entry['files']
                    if f not in deleted_files and os.path.exists(f)
                ]
    
    save_track_data(track_data)
    return deleted_files

def get_final_export_path(base_path, dir_modifier, clean_name, scope, format_type):
    """Get the final export path with directory modifiers applied"""
    extension = get_extension(format_type)
    
    if dir_modifier:
        safe_path = os.path.join(base_path, dir_modifier)
        return os.path.join(safe_path, f"{clean_name}{extension}")
    else:
        return os.path.join(base_path, f"{clean_name}{extension}")

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

def find_collection_export_roots(scene_collection):
    """Find all collection export roots with improved -sk modifier support"""
    export_roots = {}
    
    def traverse_collections(collection, current_root=None):
        """Recursively traverse collections to find export roots"""
        clean_name, modifiers = parse_modifiers(collection.name)
        
        # Skip collections with -dk modifier
        if modifiers['dk'] or not should_export_collection(collection):
            return
        
        # NEW: Handle -sk modifier (simply skip this collection but continue with children)
        if modifiers['sk']:
            # Skip this collection but continue traversing children
            for child_collection in collection.children:
                traverse_collections(child_collection, current_root)
            return
        
        # Handle -sep modifier (separate export)
        if modifiers['sep']:
            current_root = collection
            if collection not in export_roots:
                export_roots[collection] = []
        
        # Set current root if none is set
        if current_root is None:
            current_root = collection
            if collection not in export_roots:
                export_roots[collection] = []
        
        # Add collection to current root's export group
        if current_root is not None and collection not in export_roots[current_root]:
            export_roots[current_root].append(collection)
        
        # Traverse children
        for child_collection in collection.children:
            traverse_collections(child_collection, current_root)
    
    # Start traversal from scene collection children
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
    if modifiers['sk']:
        reasons.append("'-sk' modifier")
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
    obj.matrix_world.translation = world_matrix.translation + offset

def restore_original_position(obj, original_matrix):
    """Restore object to its original position"""
    obj.matrix_world = original_matrix

def safe_apply_modifiers(obj):
    """Safely apply all modifiers to an object, skipping any that fail"""
    success_count = 0
    error_count = 0
    
    # Use a while loop to safely apply modifiers as the list changes
    while obj.modifiers:
        modifier = obj.modifiers[0]
        modifier_name = modifier.name
        
        try:
            # Use temp_override for safer modifier application
            with bpy.context.temp_override(object=obj):
                bpy.ops.object.modifier_apply(modifier=modifier_name)
            success_count += 1
        except RuntimeError as e:
            print(f"⚠️ Could not apply modifier '{modifier_name}' on '{obj.name}': {str(e)}")
            error_count += 1
            # Remove the problematic modifier or break to avoid infinite loop
            try:
                obj.modifiers.remove(modifier)
            except:
                break
    
    return success_count, error_count

def export_selected(context, selected_items):
    """Export only selected objects and collections with proper collection handling"""
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
    exported_files = []
    
    try:
        # Gather all objects that need to be moved for local origins
        all_export_objects = set()
        
        # Add objects from selected collections
        for collection in selected_items['collections']:
            collection_objects = get_all_objects_from_collection(collection)
            all_export_objects.update(collection_objects)
        
        # Add directly selected objects
        for obj in selected_items['objects']:
            if should_export_object(obj):
                all_export_objects.add(obj)
        
        # Prevent viewport updates during transformation
        if prefs.export_individual_origins and all_export_objects:
            print("📍 Using local origins - moving selected items to 3D cursor...")
            
            # Store original positions and move to cursor
            for obj in all_export_objects:
                if obj and obj.matrix_world:
                    original_positions[obj] = obj.matrix_world.copy()
                    move_to_3d_cursor(obj, cursor_location)
        
        available_ops = get_available_export_operators()
        print(f"📊 Available operators: {available_ops}")
        success_count = 0
        
        # Export selected collections as individual files
        for collection in selected_items['collections']:
            col_clean, col_modifiers = parse_modifiers(collection.name)
            
            # Skip collections with -dk or -sk modifiers
            if col_modifiers['dk'] or col_modifiers['sk']:
                print(f"⏭️ Skipping collection '{col_clean}' (modifier: -dk or -sk)")
                continue
            
            export_path = get_final_export_path(scene_props.export_path, col_modifiers.get('dir'), col_clean, 'COLLECTION', scene_props.export_format)
            
            if ensure_directory_exists(export_path):
                dir_created = os.path.dirname(export_path)
                if dir_created not in created_directories:
                    print(f"📁 Created directory: {dir_created}")
                    created_directories.add(dir_created)
            
            bpy.ops.object.select_all(action='DESELECT')
            object_count = 0
            
            # Select all objects in this collection (including children)
            collection_objects = get_all_objects_from_collection(collection)
            for obj in collection_objects:
                obj.select_set(True)
                object_count += 1
            
            if object_count == 0:
                print(f"⚠️ Skipping '{col_clean}': No exportable objects")
                continue
            
            try:
                # Apply modifiers if enabled
                if prefs.apply_modifiers:
                    for obj in collection_objects:
                        success, errors = safe_apply_modifiers(obj)
                        if success > 0:
                            print(f"🔧 Applied {success} modifiers to '{obj.name}'")
                        if errors > 0:
                            print(f"⚠️ Failed to apply {errors} modifiers to '{obj.name}'")
                
                if scene_props.export_format in ['GLB', 'GLTF']:
                    bpy.ops.export_scene.gltf(
                        filepath=export_path,
                        export_format='GLB' if scene_props.export_format == 'GLB' else 'GLTF_SEPARATE',
                        use_selection=True,
                        export_apply=False,  # Already applied above if needed
                        export_animations=scene_props.apply_animations,
                        export_yup=(scene_props.export_up_axis == 'Y')
                    )
                elif scene_props.export_format == 'OBJ':
                    success = export_obj_compat(
                        filepath=export_path,
                        use_selection=True,
                        apply_modifiers=False  # Already applied above if needed
                    )
                    if not success:
                        continue
                elif scene_props.export_format == 'FBX':
                    bpy.ops.export_scene.fbx(
                        filepath=export_path,
                        use_selection=True,
                        use_mesh_modifiers=False,  # Already applied above if needed
                        bake_anim=scene_props.apply_animations,
                        axis_forward='Y',
                        axis_up='Z' if scene_props.export_up_axis == 'Z' else 'Y'
                    )
                
                print(f"✅ Exported selected collection '{col_clean}' to: {export_path}")
                success_count += 1
                exported_files.append(export_path)
            except Exception as e:
                print(f"❌ Collection export failed for '{col_clean}': {str(e)}")
        
        # Export selected objects as individual files
        for obj in selected_items['objects']:
            # Skip if object was already exported as part of a collection
            if obj in all_export_objects and any(col for col in selected_items['collections'] if obj in get_all_objects_from_collection(col)):
                print(f"⏭️ Skipping '{obj.name}' (already exported via collection)")
                continue
            
            if not should_export_object(obj):
                continue
            
            collection = get_collection_for_object(obj)
            obj_clean, obj_modifiers = parse_modifiers(obj.name)
            export_dir = resolve_export_directory(obj, collection, 'OBJECT', scene_props.export_path)
            export_path = os.path.join(export_dir, f"{obj_clean}{get_extension(scene_props.export_format)}")
            
            if ensure_directory_exists(export_path):
                dir_created = os.path.dirname(export_path)
                if dir_created not in created_directories:
                    print(f"📁 Created directory: {dir_created}")
                    created_directories.add(dir_created)
            
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            
            try:
                # Apply modifiers if enabled
                if prefs.apply_modifiers:
                    success, errors = safe_apply_modifiers(obj)
                    if success > 0:
                        print(f"🔧 Applied {success} modifiers to '{obj.name}'")
                    if errors > 0:
                        print(f"⚠️ Failed to apply {errors} modifiers to '{obj.name}'")
                
                if scene_props.export_format in ['GLB', 'GLTF']:
                    bpy.ops.export_scene.gltf(
                        filepath=export_path,
                        export_format='GLB' if scene_props.export_format == 'GLB' else 'GLTF_SEPARATE',
                        use_selection=True,
                        export_apply=False,  # Already applied above if needed
                        export_animations=scene_props.apply_animations,
                        export_yup=(scene_props.export_up_axis == 'Y')
                    )
                elif scene_props.export_format == 'OBJ':
                    success = export_obj_compat(
                        filepath=export_path,
                        use_selection=True,
                        apply_modifiers=False  # Already applied above if needed
                    )
                    if not success:
                        continue
                elif scene_props.export_format == 'FBX':
                    bpy.ops.export_scene.fbx(
                        filepath=export_path,
                        use_selection=True,
                        use_mesh_modifiers=False,  # Already applied above if needed
                        bake_anim=scene_props.apply_animations,
                        axis_forward='Y',
                        axis_up='Z' if scene_props.export_up_axis == 'Z' else 'Y'
                    )
                
                print(f"✅ Exported selected object '{obj_clean}' to: {export_path}")
                success_count += 1
                exported_files.append(export_path)
            except Exception as e:
                print(f"❌ Object export failed for '{obj_clean}': {str(e)}")
        
        return {'FINISHED'} if success_count > 0 else {'CANCELLED'}
    
    finally:
        if exported_files and prefs.enable_export_tracking:
            update_track_file(exported_files, scene_props.export_path)
            print(f"📊 Tracking updated: {len(exported_files)} files recorded")
        
        if original_positions:
            print("📍 Restoring original object positions...")
            for obj, original_matrix in original_positions.items():
                if obj:
                    obj.matrix_world = original_matrix

def export_glb(context):
    """Main export function"""
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
    exported_files = []
    
    try:
        # Prevent viewport updates during transformation
        if prefs.export_individual_origins and scene_props.export_scope != 'SCENE':
            print("📍 Using local origins - moving to 3D cursor (hidden)...")
            
            # Minimize viewport updates by doing all transformations first
            if scene_props.export_scope == 'COLLECTION':
                export_roots = find_collection_export_roots(bpy.context.scene.collection)
                for root_collection, collections_in_root in export_roots.items():
                    objects_in_root = []
                    for col in collections_in_root:
                        objects_in_root.extend([obj for obj in col.all_objects if should_export_object(obj)])
                    
                    if objects_in_root:
                        collection_positions = move_collection_to_origin(objects_in_root, cursor_location)
                        original_positions.update(collection_positions)
            
            elif scene_props.export_scope == 'OBJECT':
                for obj in bpy.data.objects:
                    if should_export_object(obj):
                        original_positions[obj] = obj.matrix_world.copy()
                        move_to_3d_cursor(obj, cursor_location)
        
        available_ops = get_available_export_operators()
        print(f"📊 Available operators: {available_ops}")
        
        if scene_props.export_scope == 'SCENE':
            scene_clean, scene_modifiers = parse_modifiers(scene_props.scene_export_filename)
            export_path = get_final_export_path(scene_props.export_path, scene_modifiers.get('dir'), scene_clean, 'SCENE', scene_props.export_format)
            
            if ensure_directory_exists(export_path):
                print(f"📁 Created directory: {os.path.dirname(export_path)}")
            
            try:
                if scene_props.export_format in ['GLB', 'GLTF']:
                    bpy.ops.export_scene.gltf(
                        filepath=export_path,
                        export_format='GLB' if scene_props.export_format == 'GLB' else 'GLTF_SEPARATE',
                        use_selection=False,
                        export_apply=prefs.apply_modifiers,
                        export_animations=scene_props.apply_animations,
                        export_yup=(scene_props.export_up_axis == 'Y')
                    )
                elif scene_props.export_format == 'OBJ':
                    success = export_obj_compat(
                        filepath=export_path,
                        use_selection=False,
                        apply_modifiers=prefs.apply_modifiers
                    )
                    if not success:
                        return {'CANCELLED'}
                elif scene_props.export_format == 'FBX':
                    bpy.ops.export_scene.fbx(
                        filepath=export_path,
                        use_selection=False,
                        use_mesh_modifiers=prefs.apply_modifiers,
                        bake_anim=scene_props.apply_animations,
                        axis_forward='Y',
                        axis_up='Z' if scene_props.export_up_axis == 'Z' else 'Y'
                    )
                
                print(f"✅ Exported scene to: {export_path}")
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
                export_path = get_final_export_path(scene_props.export_path, col_modifiers.get('dir'), col_clean, 'COLLECTION', scene_props.export_format)
                
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
                
                try:
                    if scene_props.export_format in ['GLB', 'GLTF']:
                        bpy.ops.export_scene.gltf(
                            filepath=export_path,
                            export_format='GLB' if scene_props.export_format == 'GLB' else 'GLTF_SEPARATE',
                            use_selection=True,
                            export_apply=prefs.apply_modifiers,
                            export_animations=scene_props.apply_animations,
                            export_yup=(scene_props.export_up_axis == 'Y')
                        )
                    elif scene_props.export_format == 'OBJ':
                        success = export_obj_compat(
                            filepath=export_path,
                            use_selection=True,
                            apply_modifiers=prefs.apply_modifiers
                        )
                        if not success:
                            continue
                    elif scene_props.export_format == 'FBX':
                        bpy.ops.export_scene.fbx(
                            filepath=export_path,
                            use_selection=True,
                            use_mesh_modifiers=prefs.apply_modifiers,
                            bake_anim=scene_props.apply_animations,
                            axis_forward='Y',
                            axis_up='Z' if scene_props.export_up_axis == 'Z' else 'Y'
                        )
                    
                    collection_list = ", ".join([parse_modifiers(col.name)[0] for col in collections_in_root])
                    print(f"✅ Exported '{col_clean}' to: {export_path}")
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
                export_path = os.path.join(export_dir, f"{obj_clean}{get_extension(scene_props.export_format)}")
                
                if ensure_directory_exists(export_path):
                    dir_created = os.path.dirname(export_path)
                    if dir_created not in created_directories:
                        print(f"📁 Created directory: {dir_created}")
                        created_directories.add(dir_created)
                
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                
                try:
                    if scene_props.export_format in ['GLB', 'GLTF']:
                        bpy.ops.export_scene.gltf(
                            filepath=export_path,
                            export_format='GLB' if scene_props.export_format == 'GLB' else 'GLTF_SEPARATE',
                            use_selection=True,
                            export_apply=prefs.apply_modifiers,
                            export_animations=scene_props.apply_animations,
                            export_yup=(scene_props.export_up_axis == 'Y')
                        )
                    elif scene_props.export_format == 'OBJ':
                        success = export_obj_compat(
                            filepath=export_path,
                            use_selection=True,
                            apply_modifiers=prefs.apply_modifiers
                        )
                        if not success:
                            continue
                    elif scene_props.export_format == 'FBX':
                        bpy.ops.export_scene.fbx(
                            filepath=export_path,
                            use_selection=True,
                            use_mesh_modifiers=prefs.apply_modifiers,
                            bake_anim=scene_props.apply_animations,
                            axis_forward='Y',
                            axis_up='Z' if scene_props.export_up_axis == 'Z' else 'Y'
                        )
                    
                    print(f"✅ Exported '{obj_clean}' to: {export_path}")
                    success_count += 1
                    exported_files.append(export_path)
                except Exception as e:
                    print(f"❌ Object export failed for '{obj_clean}': {str(e)}")
            
            return {'FINISHED'} if success_count > 0 else {'CANCELLED'}
        
        return {'CANCELLED'}
    
    finally:
        if exported_files and prefs.enable_export_tracking:
            update_track_file(exported_files, scene_props.export_path)
            print(f"📊 Tracking updated: {len(exported_files)} files recorded")
        
        if original_positions:
            print("📍 Restoring original object positions...")
            
            if scene_props.export_scope == 'COLLECTION' and prefs.export_individual_origins:
                collection_groups = {}
                export_roots = find_collection_export_roots(bpy.context.scene.collection)
                
                for root_collection, collections_in_root in export_roots.items():
                    objects_in_root = []
                    for col in collections_in_root:
                        objects_in_root.extend([obj for obj in col.all_objects if obj in original_positions])
                    
                    if objects_in_root:
                        for obj in objects_in_root:
                            if obj in original_positions:
                                obj.matrix_world = original_positions[obj]
                
                for obj, original_matrix in original_positions.items():
                    if obj and obj not in collection_groups:
                        obj.matrix_world = original_matrix
            else:
                for obj, original_matrix in original_positions.items():
                    if obj:
                        obj.matrix_world = original_matrix

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
    bpy.utils.register_class(ADVANCED_GLB_OT_export_selected)
    bpy.utils.register_class(ADVANCED_GLB_OT_delete_track_file)
    bpy.utils.register_class(ADVANCED_GLB_OT_execute_order_66)
    bpy.utils.register_class(ADVANCED_GLB_OT_validate_sk_modifiers)
    bpy.utils.register_class(ADVANCED_GLB_PT_panel)
    bpy.utils.register_class(AdvancedGLBPreferences)
    bpy.utils.register_class(AdvancedGLBSceneProperties)
    
    bpy.types.Scene.advanced_glb_props = bpy.props.PointerProperty(type=AdvancedGLBSceneProperties)
    
    if on_save_handler not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(on_save_handler)

def unregister():
    # Clean up any running exports
    ExportState.is_exporting = False
    
    bpy.utils.unregister_class(ADVANCED_GLB_OT_export)
    bpy.utils.unregister_class(ADVANCED_GLB_OT_export_selected)
    bpy.utils.unregister_class(ADVANCED_GLB_OT_delete_track_file)
    bpy.utils.unregister_class(ADVANCED_GLB_OT_execute_order_66)
    bpy.utils.unregister_class(ADVANCED_GLB_OT_validate_sk_modifiers)
    bpy.utils.unregister_class(ADVANCED_GLB_PT_panel)
    bpy.utils.unregister_class(AdvancedGLBPreferences)
    bpy.utils.unregister_class(AdvancedGLBSceneProperties)
    
    del bpy.types.Scene.advanced_glb_props
    
    if on_save_handler in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(on_save_handler)

if __name__ == "__main__":
    register()
