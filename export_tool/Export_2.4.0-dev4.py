bl_info = {
    "name": "Advanced Auto-Exporter",
    "author": "WildStar Studios", 
    "version": (2, 4, 0, "dev 4"),
    "blender": (2, 8, 0),
    "location": "View3D > Sidebar > Export",
    "description": "Advanced export with enhanced compatibility and visibility controls",
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

# ===== ENHANCED COMPATIBILITY SHIMS =====
def get_blender_version():
    """Get Blender version as tuple for precise compatibility checks"""
    return bpy.app.version

def is_blender_version_or_newer(major, minor=0, patch=0):
    """Check if running on specified Blender version or newer"""
    return bpy.app.version >= (major, minor, patch)

def get_selected_ids_compat(context):
    """Enhanced compatibility wrapper for getting selected IDs"""
    selected_objects = context.selected_objects
    selected_collections = []
    
    # Method 1: Try modern selected_ids (Blender 3.0+)
    if hasattr(context, 'selected_ids') and context.selected_ids:
        for item in context.selected_ids:
            if hasattr(item, 'name') and hasattr(item, 'objects'):
                selected_collections.append(item)
        return {'objects': selected_objects, 'collections': selected_collections}
    
    # Method 2: Try outliner space selection (Blender 2.8-2.93)
    try:
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'OUTLINER':
                    space = area.spaces.active
                    if hasattr(space, 'selected_ids'):
                        for item in space.selected_ids:
                            if hasattr(item, 'name') and hasattr(item, 'objects'):
                                selected_collections.append(item)
                    break
    except Exception as e:
        print(f"Debug: Outliner selection fallback failed: {e}")
    
    # Method 3: Collection selection via scene (universal fallback)
    try:
        for collection in bpy.data.collections:
            if getattr(collection, 'select_get', lambda: False)():
                selected_collections.append(collection)
    except Exception as e:
        print(f"Debug: Collection selection fallback failed: {e}")
    
    return {
        'objects': selected_objects,
        'collections': selected_collections
    }

def temp_override_compat(**kwargs):
    """Enhanced compatibility wrapper for temp_override"""
    if hasattr(bpy.context, 'temp_override') and is_blender_version_or_newer(3, 2):
        return bpy.context.temp_override(**kwargs)
    else:
        # For Blender 2.8-3.1, use a simple context manager
        class DummyContext:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
        return DummyContext()

# ===== ENHANCED OPERATORS =====
class ADVANCED_GLB_OT_export(bpy.types.Operator):
    bl_idname = "export.advanced_glb"
    bl_label = "Export"
    bl_description = "Export using current settings"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        """Show confirmation dialog if enabled in preferences"""
        prefs = context.preferences.addons[__name__].preferences
        if prefs.enable_export_confirmation:
            return context.window_manager.invoke_props_dialog(self)
        else:
            return self.execute(context)

    def draw(self, context):
        layout = self.layout
        scene_props = context.scene.advanced_glb_props
        
        layout.label(text="Confirm Export", icon='EXPORT')
        
        # Show export summary
        stats = self.get_export_stats(scene_props)
        for stat in stats:
            layout.label(text=stat)
        
        if scene_props.export_scope == 'SCENE':
            clean_name, _ = parse_modifiers(scene_props.scene_export_filename)
            layout.label(text=f"File: {clean_name}{get_extension(scene_props.export_format)}")
        else:
            layout.label(text=f"Scope: {scene_props.export_scope.title()}s")
        
        layout.label(text=f"Mode: {scene_props.export_mode.title()}")

    def get_export_stats(self, scene_props):
        """Get export statistics for confirmation dialog"""
        stats = []
        export_mode = scene_props.export_mode
        
        if scene_props.export_scope == 'SCENE':
            objects = [obj for obj in bpy.data.objects if should_export_object(obj, export_mode)]
            stats.append(f"Objects to export: {len(objects)}")
        elif scene_props.export_scope == 'COLLECTION':
            roots = find_collection_export_roots(bpy.context.scene.collection, export_mode)
            object_count = sum(
                len([obj for obj in col.all_objects if should_export_object(obj, export_mode)])
                for root_col, collections in roots.items()
                for col in collections
            )
            stats.append(f"Collections to export: {len(roots)}")
            stats.append(f"Objects to export: {object_count}")
        elif scene_props.export_scope == 'OBJECT':
            objects = [obj for obj in bpy.data.objects if should_export_object(obj, export_mode)]
            stats.append(f"Objects to export: {len(objects)}")
            
        return stats

    def execute(self, context):
        scene_props = context.scene.advanced_glb_props
        
        if ExportState.is_exporting:
            self.report({'WARNING'}, "Export already in progress. Please wait.")
            return {'CANCELLED'}
        
        # Enhanced animation warnings with version-specific checks
        if scene_props.apply_animations:
            if scene_props.export_format in ['OBJ']:
                self.report({'WARNING'}, f"{scene_props.export_format} format doesn't support animations!")
        
        ExportState.is_exporting = True
        try:
            result = export_glb(context)
            if result == {'FINISHED'}:
                mode_display = scene_props.export_mode.title()
                self.report({'INFO'}, f"Exported {mode_display} {scene_props.export_scope.lower()} to {scene_props.export_path}")
            return result
        finally:
            ExportState.is_exporting = False

class ADVANCED_GLB_OT_export_selected(bpy.types.Operator):
    bl_idname = "export.advanced_glb_selected"
    bl_label = "Export Selected"
    bl_description = "Export only the currently selected collections or objects"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        """Show confirmation dialog if enabled in preferences"""
        prefs = context.preferences.addons[__name__].preferences
        if prefs.enable_export_confirmation:
            return context.window_manager.invoke_props_dialog(self)
        else:
            return self.execute(context)

    def draw(self, context):
        layout = self.layout
        scene_props = context.scene.advanced_glb_props
        
        layout.label(text="Confirm Selected Export", icon='EXPORT')
        
        selected_items = get_selected_items(context)
        export_type = scene_props.selected_export_type
        
        obj_count = len(selected_items['objects'])
        col_count = len(selected_items['collections'])
        
        layout.label(text=f"Export Type: {export_type.title()}")
        layout.label(text=f"Selected Objects: {obj_count}")
        layout.label(text=f"Selected Collections: {col_count}")
        layout.label(text=f"Mode: {scene_props.export_mode.title()}")

    def execute(self, context):
        scene_props = context.scene.advanced_glb_props
        
        if ExportState.is_exporting:
            self.report({'WARNING'}, "Export already in progress. Please wait.")
            return {'CANCELLED'}
        
        selected_items = get_selected_items(context)
        
        if not selected_items['objects'] and not selected_items['collections']:
            self.report({'WARNING'}, "No objects or collections selected")
            return {'CANCELLED'}
        
        # Enhanced validation based on selected export type
        export_type = scene_props.selected_export_type
        if export_type == 'COLLECTION' and not selected_items['collections']:
            self.report({'WARNING'}, "No collections selected for collection export")
            return {'CANCELLED'}
        elif export_type == 'OBJECT' and not selected_items['objects']:
            self.report({'WARNING'}, "No objects selected for object export")
            return {'CANCELLED'}
        
        ExportState.is_exporting = True
        try:
            result = export_selected(context, selected_items)
            if result == {'FINISHED'}:
                export_type = scene_props.selected_export_type
                if export_type == 'COLLECTION':
                    col_count = len(selected_items['collections'])
                    self.report({'INFO'}, f"Exported {col_count} collections to {scene_props.export_path}")
                else:
                    obj_count = len(selected_items['objects'])
                    self.report({'INFO'}, f"Exported {obj_count} objects to {scene_props.export_path}")
            return result
        finally:
            ExportState.is_exporting = False

# ===== NEW HIGHLIGHT OPERATOR =====
class ADVANCED_GLB_OT_highlight_exportable(bpy.types.Operator):
    bl_idname = "advanced_glb.highlight_exportable"
    bl_label = "Highlight Exportable"
    bl_description = "Select all objects that will be exported with current settings"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene_props = context.scene.advanced_glb_props
        export_mode = scene_props.export_mode
        
        # Deselect all first
        bpy.ops.object.select_all(action='DESELECT')
        
        objects_to_select = []
        
        if scene_props.export_scope == 'SCENE':
            # Select all exportable objects in the scene
            for obj in bpy.data.objects:
                if should_export_object(obj, export_mode):
                    objects_to_select.append(obj)
                    
        elif scene_props.export_scope == 'COLLECTION':
            # Select objects from exportable collections
            export_roots = find_collection_export_roots(bpy.context.scene.collection, export_mode)
            for root_col, collections in export_roots.items():
                for col in collections:
                    for obj in col.all_objects:
                        if should_export_object(obj, export_mode):
                            objects_to_select.append(obj)
                            
        elif scene_props.export_scope == 'OBJECT':
            # Select individual exportable objects
            for obj in bpy.data.objects:
                if should_export_object(obj, export_mode):
                    objects_to_select.append(obj)
        
        # Select the objects
        for obj in objects_to_select:
            obj.select_set(True)
        
        # Set active object if any were selected
        if objects_to_select:
            context.view_layer.objects.active = objects_to_select[0]
            self.report({'INFO'}, f"Selected {len(objects_to_select)} exportable objects")
        else:
            self.report({'WARNING'}, "No exportable objects found with current settings")
            
        return {'FINISHED'}

# ===== ENHANCED ORDER 66 OPERATOR =====
class ADVANCED_GLB_OT_execute_order_66(bpy.types.Operator):
    bl_idname = "advanced_glb.execute_order_66"
    bl_label = "Execute Order 66"
    bl_description = "Delete orphaned files based on tracking data"
    bl_options = {'REGISTER'}
    
    # NEW: Option to include empty folders in cleanup
    cleanup_empty_folders: BoolProperty(
        name="Cleanup Empty Folders",
        default=False,
        description="Also delete empty folders in export directory"
    )
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="This will delete orphaned files.", icon='ERROR')
        layout.label(text="This action cannot be undone!")
        
        # NEW: Show cleanup options
        layout.prop(self, "cleanup_empty_folders")
        
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
        deleted_files = cleanup_orphaned_files(self.cleanup_empty_folders)
        if deleted_files:
            self.report({'INFO'}, f"Executed Order 66: Deleted {len(deleted_files)} orphaned files")
        else:
            self.report({'INFO'}, "No orphaned files found to delete")
        return {'FINISHED'}

# ===== ENHANCED DELETE TRACK FILE OPERATOR WITH CONFIRMATION =====
class ADVANCED_GLB_OT_delete_track_file(bpy.types.Operator):
    bl_idname = "advanced_glb.delete_track_file"
    bl_label = "Delete Track File"
    bl_description = "Delete the export tracking file for this blend file"
    bl_options = {'REGISTER'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="Delete export tracking file?", icon='ERROR')
        layout.label(text="This will remove export history tracking.")
        
        track_file_path = get_track_file_path()
        if os.path.exists(track_file_path):
            layout.label(text=f"File: {os.path.basename(track_file_path)}")
        else:
            layout.label(text="No track file found", icon='INFO')
    
    def execute(self, context):
        track_file_path = get_track_file_path()
        if os.path.exists(track_file_path):
            os.remove(track_file_path)
            self.report({'INFO'}, f"Deleted track file: {os.path.basename(track_file_path)}")
        else:
            self.report({'WARNING'}, "No track file found")
        return {'FINISHED'}

# ===== NEW VALIDATE EXPORT MODIFIERS OPERATOR =====
class ADVANCED_GLB_OT_validate_export_modifiers(bpy.types.Operator):
    bl_idname = "advanced_glb.validate_export_modifiers"
    bl_label = "Validate Export Modifiers"
    bl_description = "Check for incompatible modifier combinations and validate -sk usage"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        prefs = context.preferences.addons[__name__].preferences
        issues = validate_export_modifiers(prefs.sk_behavior)
        
        if not issues:
            self.report({'INFO'}, "All modifiers are valid")
            return {'FINISHED'}
        
        def draw_report(self, context):
            layout = self.layout
            for issue in issues:
                if issue['type'] == 'ERROR':
                    layout.label(text=f"❌ {issue['message']}", icon='ERROR')
                else:
                    layout.label(text=f"⚠️ {issue['message']}", icon='INFO')
        
        context.window_manager.popup_menu(draw_report, title="Export Modifier Issues", icon='ERROR')
        
        error_count = sum(1 for issue in issues if issue['type'] == 'ERROR')
        warning_count = sum(1 for issue in issues if issue['type'] == 'WARNING')
        
        self.report({'WARNING'}, f"Found {error_count} errors, {warning_count} warnings")
        return {'FINISHED'}

# ===== ENHANCED PROPERTIES =====
class AdvancedGLBSceneProperties(bpy.types.PropertyGroup):
    export_path: StringProperty(
        name="Export Path",
        subtype='DIR_PATH',
        default="",
        description="Directory path for exports"
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
    
    # CHANGED: Export Mode as dropdown (removed expand=True)
    export_mode: EnumProperty(
        name="Export Mode",
        items=[
            ('ALL', "All Objects", "Export all objects regardless of visibility"),
            ('VISIBLE', "Visible Only", "Export only visible objects"),
            ('RENDERABLE', "Render Only", "Export only renderable objects"),
        ],
        default='VISIBLE',
        description="Control which objects to export based on visibility and renderability"
    )
    
    # NEW: Selected Export Type
    selected_export_type: EnumProperty(
        name="Export Selected As",
        items=[
            ('COLLECTION', "Collections", "Export selected items as collections"),
            ('OBJECT', "Objects", "Export selected items as individual objects"),
        ],
        default='COLLECTION',
        description="How to handle selected items export"
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

# ===== ENHANCED PREFERENCES =====
class AdvancedGLBPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    # REORDERED: Auto-export first
    auto_export_on_save: BoolProperty(
        name="Auto Export on Save",
        default=True,
        description="Automatically export when saving the Blender file"
    )
    
    apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        default=True,
        description="Apply modifiers before export"
    )
    
    export_individual_origins: BoolProperty(
        name="Export with Local Origins",
        default=True,
        description="Export each object/collection with its local origin at (0,0,0) by moving to 3D cursor"
    )
    
    apply_animations: BoolProperty(
        name="Apply Animations",
        default=False,
        description="Include animations in export (if format supports it)"
    )
    
    # NEW: Export confirmation setting
    enable_export_confirmation: BoolProperty(
        name="Enable Export Confirmation",
        default=True,
        description="Show confirmation dialog before exporting"
    )
    
    # NEW: -sk behavior setting
    sk_behavior: EnumProperty(
        name="-sk Behavior",
        items=[
            ('BASIC', "Basic", "Skip collections without validation"),
            ('STRICT', "Strict", "Validate -sk usage and prevent export if issues found"),
        ],
        default='BASIC',
        description="How to handle -sk modifier validation"
    )
    
    # ENHANCED: Show details as a proper expandable section
    show_detailed_list: BoolProperty(
        name="Show Export Preview",
        default=False,
        description="Show detailed preview of what will be exported"
    )
    
    show_hidden_objects: BoolProperty(
        name="Show Hidden in Preview",
        default=False,
        description="Include hidden objects in the export preview"
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
        
        # Main settings - REORDERED
        main_box = layout.box()
        main_box.label(text="Export Behavior", icon='EXPORT')
        main_box.prop(self, "auto_export_on_save")
        main_box.prop(self, "apply_modifiers")
        main_box.prop(self, "export_individual_origins")
        main_box.prop(self, "apply_animations")
        main_box.prop(self, "enable_export_confirmation")
        main_box.prop(self, "sk_behavior")
        
        # Display settings - ENHANCED
        display_box = layout.box()
        display_box.label(text="Display Options", icon='VIEW3D')
        display_box.prop(self, "show_detailed_list")
        
        # Only show hidden objects toggle when details are enabled
        if self.show_detailed_list:
            display_box.prop(self, "show_hidden_objects")
        
        # Tracking settings
        track_box = layout.box()
        track_box.label(text="File Tracking", icon='FILE_ARCHIVE')
        track_box.prop(self, "enable_export_tracking")
        
        if self.enable_export_tracking:
            track_box.prop(self, "track_file_location")
            
            # FIXED: Swapped button order in preferences too
            row = track_box.row()
            row.operator("advanced_glb.execute_order_66", text="Clean Orphans", icon='COMMUNITY')
            row.operator("advanced_glb.delete_track_file", text="Delete Track File", icon='TRASH')

# ===== ENHANCED UI PANEL =====
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
        version_box.label(text="🚀 Version 2.4.0 dev4", icon='EXPERIMENTAL')
        version_box.label(text=f"✓ Enhanced Blender 2.8-4.5 Support", icon='CHECKMARK')
        
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
        
        # CHANGED: Export Mode as dropdown with highlight button next to it
        mode_row = quick_box.row(align=True)
        mode_row.label(text="Export Mode:")
        mode_row.prop(scene_props, "export_mode", text="")
        # NEW: Highlight button moved next to export mode
        highlight_op = mode_row.operator("advanced_glb.highlight_exportable", text="", icon='RESTRICT_SELECT_OFF')
        
        # Up Axis
        quick_box.prop(scene_props, "export_up_axis", expand=True)
        
        # Scene filename when in scene mode
        if scene_props.export_scope == 'SCENE':
            row = quick_box.row(align=True)
            row.label(text="Filename:")
            row.prop(scene_props, "scene_export_filename", text="")
        
        # Enhanced animation warnings with mode info
        if scene_props.apply_animations:
            if scene_props.export_format in ['OBJ']:
                quick_box.label(text="⚠️ OBJ doesn't support animations!", icon='ERROR')
            else:
                mode_info = f" ({scene_props.export_mode} objects only)"
                quick_box.label(text=f"✓ Animations enabled{mode_info}", icon='CHECKMARK')
        
        # Enhanced stats with mode information
        stats = self.get_enhanced_quick_stats(scene_props)
        if stats:
            stats_box = quick_box.box()
            for stat in stats:
                stats_box.label(text=stat)
        
        # Export buttons
        button_text = self.get_enhanced_export_button_text(scene_props)
        
        if ExportState.is_exporting:
            export_row = quick_box.row()
            export_row.enabled = False
            export_row.operator("export.advanced_glb", text="Exporting...", icon='LOADING')
            quick_box.label(text="Export in progress...", icon='TIME')
        else:
            # Main export button
            export_row = quick_box.row()
            export_op = export_row.operator("export.advanced_glb", text=button_text, icon='EXPORT')
            
            # ENHANCED: Selected export with dropdown
            selected_items = get_selected_items(context)
            if selected_items['objects'] or selected_items['collections']:
                select_box = quick_box.box()
                select_box.label(text="Export Selected:", icon='SELECT_SET')
                
                # NEW: Selected export type dropdown
                row = select_box.row(align=True)
                row.prop(scene_props, "selected_export_type", expand=True)
                
                select_label = self.get_enhanced_select_export_label(selected_items, scene_props)
                select_box.operator("export.advanced_glb_selected", text=select_label, icon='EXPORT')
        
        # === SETTINGS SECTION - REORDERED ===
        settings_box = layout.box()
        settings_box.label(text="Settings", icon='PREFERENCES')
        
        # REORDERED: Auto-export first, then apply modifiers, then local origins, then animations
        settings_box.prop(prefs, "auto_export_on_save")
        settings_box.prop(prefs, "apply_modifiers")
        
        # Disable local origins for scene export
        local_origins_row = settings_box.row()
        local_origins_row.prop(prefs, "export_individual_origins")
        if scene_props.export_scope == 'SCENE':
            local_origins_row.enabled = False
        
        settings_box.prop(prefs, "apply_animations")
        
        # ENHANCED: Show Export Preview (formerly Show Details)
        settings_box.prop(prefs, "show_detailed_list", text="Show Export Preview")
        
        # Only show hidden objects toggle when preview is enabled
        if prefs.show_detailed_list:
            settings_box.prop(prefs, "show_hidden_objects")
        
        # === MODIFIERS INFO ===
        mod_box = layout.box()
        mod_box.label(text="Name Modifiers", icon='SYNTAX_OFF')
        
        mod_grid = mod_box.grid_flow(columns=2, align=True)
        mod_grid.label(text="• -dir:folder → Organize in subfolder")
        mod_grid.label(text="• -sep → Export collection separately")
        mod_grid.label(text="• -dk → Don't export this item")  
        mod_grid.label(text="• -sk → Skip collection (ignore)")
        mod_grid.label(text="• -anim → Include animations")
        mod_grid.label(text="• Visibility → Controlled by Export Mode")
        
        # NEW: Validation button - disabled for scene export
        validation_row = mod_box.row()
        validation_row.operator("advanced_glb.validate_export_modifiers", icon='CHECKMARK')
        if scene_props.export_scope == 'SCENE':
            validation_row.enabled = False
        
        # === ENHANCED TRACKING SYSTEM ===
        if prefs.enable_export_tracking:
            track_box = layout.box()
            track_box.label(text="File Tracking", icon='FILE_ARCHIVE')
            
            track_box.prop(prefs, "track_file_location", expand=True)
            
            # FIXED: Swapped button order - Clean Orphans on left, Delete Track File on right
            row = track_box.row(align=True)
            row.operator("advanced_glb.execute_order_66", text="Clean Orphans")
            row.operator("advanced_glb.delete_track_file", text="Delete Track File")
        
        # === ENHANCED EXPORT PREVIEW (formerly Detailed View) ===
        if prefs.show_detailed_list:
            preview_box = layout.box()
            preview_box.label(text="Export Preview", icon='INFO')
            
            # Add a note about what will be exported
            preview_box.label(text="Objects that will be exported:")
            
            details = self.get_enhanced_export_preview(scene_props, prefs)
            if details:
                for detail in details:
                    preview_box.label(text=detail)
            else:
                preview_box.label(text="No objects will be exported with current settings")

    def get_enhanced_quick_stats(self, scene_props):
        """Enhanced statistics with mode information"""
        if not scene_props.export_path:
            return []
            
        stats = []
        export_mode = scene_props.export_mode
        
        if ExportState.is_exporting:
            stats.append("🔄 Export in progress...")
            return stats
            
        if scene_props.export_scope == 'SCENE':
            objects = [obj for obj in bpy.data.objects if should_export_object(obj, export_mode)]
            stats.append(f"📦 Scene ({export_mode}): {len(objects)} objects")
            
        elif scene_props.export_scope == 'COLLECTION':
            roots = find_collection_export_roots(bpy.context.scene.collection, export_mode)
            object_count = sum(
                len([obj for obj in col.all_objects if should_export_object(obj, export_mode)])
                for root_col, collections in roots.items()
                for col in collections
            )
            stats.append(f"📦 Collections ({export_mode}): {len(roots)}")
            stats.append(f"📊 Objects: {object_count}")
            
        elif scene_props.export_scope == 'OBJECT':
            objects = [obj for obj in bpy.data.objects if should_export_object(obj, export_mode)]
            stats.append(f"📦 Objects ({export_mode}): {len(objects)}")
            
        return stats

    def get_enhanced_export_button_text(self, scene_props):
        """Enhanced export button text with mode info"""
        if ExportState.is_exporting:
            return "Exporting..."
        
        mode_text = scene_props.export_mode.title()
        if scene_props.export_scope == 'SCENE':
            clean_name, _ = parse_modifiers(scene_props.scene_export_filename)
            return f"Export {mode_text} {clean_name}"
        else:
            scope_text = scene_props.export_scope.title()
            return f"Export {mode_text} {scope_text}s"

    def get_enhanced_select_export_label(self, selected_items, scene_props):
        """Enhanced selected export label with type info"""
        obj_count = len(selected_items['objects'])
        col_count = len(selected_items['collections'])
        export_type = scene_props.selected_export_type
        
        if export_type == 'COLLECTION':
            if obj_count > 0 and col_count > 0:
                return f"Export ({obj_count} obj, {col_count} col)"
            elif obj_count > 0:
                return f"Export ({obj_count} objects)"
            elif col_count > 0:
                return f"Export ({col_count} collections)"
        else:  # OBJECT
            if obj_count > 0:
                return f"Export ({obj_count} objects)"
        
        return "Export Selected"

    def get_enhanced_export_preview(self, scene_props, prefs):
        """Enhanced export preview with better organization"""
        details = []
        export_mode = scene_props.export_mode
        
        if scene_props.export_scope == 'SCENE':
            objects = [obj for obj in bpy.data.objects if should_export_object(obj, export_mode)]
            clean_name, modifiers = parse_modifiers(scene_props.scene_export_filename)
            
            details.append(f"File: {clean_name}{get_extension(scene_props.export_format)}")
            if modifiers.get('dir'):
                details.append(f"Directory: {modifiers['dir']}")
            
            # Show objects that will be exported
            if objects:
                details.append("Objects to export:")
                for obj in objects[:8]:  # Show first 8 objects
                    obj_clean, _ = parse_modifiers(obj.name)
                    details.append(f"  • {obj_clean}")
                if len(objects) > 8:
                    details.append(f"  ... and {len(objects) - 8} more")
            else:
                details.append("No objects will be exported")

        elif scene_props.export_scope == 'COLLECTION':
            roots = find_collection_export_roots(bpy.context.scene.collection, export_mode)
            if roots:
                details.append(f"Collections to export ({export_mode}):")
                
                for root_col, collections in roots.items():
                    clean_name, modifiers = parse_modifiers(root_col.name)
                    obj_count = sum(len([obj for obj in col.all_objects if should_export_object(obj, export_mode)]) for col in collections)
                    dir_info = f" → {modifiers['dir']}" if modifiers.get('dir') else ""
                    details.append(f"• {clean_name}{dir_info}: {obj_count} objects")
            else:
                details.append("No collections will be exported")

        elif scene_props.export_scope == 'OBJECT':
            objects = [obj for obj in bpy.data.objects if should_export_object(obj, export_mode)]
            if objects:
                details.append(f"Objects to export ({export_mode}):")
                
                for obj in objects[:8]:  # Show first 8 objects
                    clean_name, modifiers = parse_modifiers(obj.name)
                    collection = get_collection_for_object(obj)
                    dir_info = ""
                    if collection:
                        _, col_modifiers = parse_modifiers(collection.name)
                        if col_modifiers.get('dir'):
                            dir_info = f" → {col_modifiers['dir']}"
                    details.append(f"• {clean_name}{dir_info}")
                    
                if len(objects) > 8:
                    details.append(f"  ... and {len(objects) - 8} more")
            else:
                details.append("No objects will be exported")
                
        return details

# ===== BUG FIXES FOR VISIBILITY SYSTEM =====

def is_object_visible(obj, mode='VISIBLE'):
    """
    FIXED: Enhanced visibility checking based on export mode
    Now properly accounts for collection render settings in RENDERABLE mode
    """
    if mode == 'ALL':
        return True
    elif mode == 'VISIBLE':
        # Object is visible if not hidden in viewport and not hidden in render
        # AND not in a hidden collection
        if obj.hide_viewport or obj.hide_render:
            return False
        
        # Check if object is in any visible collection
        for collection in obj.users_collection:
            if not collection.hide_viewport:
                return True
        return False
        
    elif mode == 'RENDERABLE':
        # FIXED: Object is renderable if not hidden from render AND not in a collection hidden from render
        if obj.hide_render:
            return False
            
        # Check if object is in any collection that is not hidden from render
        for collection in obj.users_collection:
            if not collection.hide_render:
                return True
        return False
        
    return True

def should_export_object(obj, export_mode='VISIBLE'):
    """
    FIXED: Enhanced object export decision with proper render mode support
    """
    clean_name, modifiers = parse_modifiers(obj.name)
    
    # Always exclude objects with -dk modifier
    if modifiers['dk']:
        return False
    
    # Check object type compatibility
    if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'ARMATURE'}:
        return False
    
    # Use fixed visibility system based on export mode
    return is_object_visible(obj, export_mode)

def should_export_collection(col, export_mode='VISIBLE'):
    """
    FIXED: Enhanced collection export decision with proper render mode support
    """
    clean_name, modifiers = parse_modifiers(col.name)
    
    if modifiers['dk']:
        return False
    
    # For RENDERABLE mode, check if collection itself is renderable
    if export_mode == 'RENDERABLE':
        if col.hide_render:
            return False
    
    # For collections, check if they contain any exportable objects
    for obj in col.all_objects:
        if should_export_object(obj, export_mode):
            return True
    
    # Also check child collections
    for child_col in col.children:
        if should_export_collection(child_col, export_mode):
            return True
    
    return False

def get_all_objects_from_collection(collection, export_mode='VISIBLE'):
    """FIXED: Get all exportable objects from a collection based on export mode"""
    objects = []
    
    def traverse_collection(col):
        # Add objects from this collection that match the export mode
        for obj in col.objects:
            if should_export_object(obj, export_mode):
                objects.append(obj)
        # Traverse child collections
        for child_col in col.children:
            traverse_collection(child_col)
    
    traverse_collection(collection)
    return objects

def find_collection_export_roots(scene_collection, export_mode='VISIBLE'):
    """FIXED: Find collection export roots with enhanced mode support"""
    export_roots = {}
    
    def traverse_collections(collection, current_root=None):
        clean_name, modifiers = parse_modifiers(collection.name)
        
        # Skip collections with -dk modifier
        if modifiers['dk']:
            return
        
        # Handle -sk modifier (skip this collection but continue with children)
        if modifiers['sk']:
            for child_collection in collection.children:
                traverse_collections(child_collection, current_root)
            return
        
        # For RENDERABLE mode, check if collection should be exported based on its render setting
        if export_mode == 'RENDERABLE':
            if collection.hide_render and not modifiers['sep']:
                # In render mode, only export collections that are actually renderable
                # unless they have -sep modifier
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
    
    for child_collection in scene_collection.children:
        traverse_collections(child_collection)
    
    return export_roots

# ===== NEW VALIDATION FUNCTIONS =====
def validate_export_modifiers(sk_behavior='BASIC'):
    """
    Validate export modifiers for incompatible combinations and -sk usage
    Returns list of issues with type and message
    """
    issues = []
    
    # Check collections
    for collection in bpy.data.collections:
        clean_name, modifiers = parse_modifiers(collection.name)
        
        # BASIC MODE: Only check for incompatible modifiers
        if sk_behavior == 'BASIC':
            # Check for incompatible modifiers
            if modifiers['sk'] and modifiers['dk']:
                issues.append({
                    'type': 'ERROR',
                    'message': f"Collection '{clean_name}': -sk and -dk are incompatible (conflicting exclusion)"
                })
            
            if modifiers['sk'] and modifiers['sep']:
                issues.append({
                    'type': 'ERROR', 
                    'message': f"Collection '{clean_name}': -sk and -sep are incompatible (conflicting collection behavior)"
                })
            
            if modifiers['sk'] and modifiers['dir']:
                issues.append({
                    'type': 'WARNING',
                    'message': f"Collection '{clean_name}': -dir modifier will be ignored because collection is skipped (-sk)"
                })
            
            if modifiers['dk'] and modifiers['anim']:
                issues.append({
                    'type': 'WARNING',
                    'message': f"Collection '{clean_name}': -anim modifier will be ignored because collection is excluded (-dk)"
                })
        
        # STRICT MODE: Only check -sk usage validation (exclude basic modifier conflicts)
        elif sk_behavior == 'STRICT' and modifiers['sk']:
            # Check if collection has no children and no objects
            if not collection.children and not collection.objects:
                issues.append({
                    'type': 'ERROR',
                    'message': f"Collection '{clean_name}': -sk used on empty collection (strict mode)"
                })
            # Check if collection has only objects (no sub-collections)
            elif not collection.children and collection.objects:
                issues.append({
                    'type': 'ERROR', 
                    'message': f"Collection '{clean_name}': -sk used on collection with only objects (strict mode)"
                })
    
    # Check objects (these run in both modes since they're not -sk specific)
    for obj in bpy.data.objects:
        clean_name, modifiers = parse_modifiers(obj.name)
        
        # Check for incompatible modifiers (applies to both BASIC and STRICT modes)
        if modifiers['dk'] and modifiers['anim']:
            issues.append({
                'type': 'WARNING',
                'message': f"Object '{clean_name}': -anim modifier will be ignored because object is excluded (-dk)"
            })
    
    return issues

# ===== ENHANCED TRACKING SYSTEM =====
def update_track_file(exported_files, export_path):
    """Enhanced tracking that includes export settings for better cleanup"""
    prefs = bpy.context.preferences.addons[__name__].preferences
    if not prefs.enable_export_tracking:
        return
    
    scene_props = bpy.context.scene.advanced_glb_props
    track_data = load_track_data()
    
    # Create a unique key based on export settings to handle scope/mode changes
    settings_key = f"{export_path}|{scene_props.export_scope}|{scene_props.export_mode}"
    
    if settings_key not in track_data:
        track_data[settings_key] = {}
    
    # Store current export settings along with files
    track_data[settings_key]['last_export'] = {
        'timestamp': datetime.datetime.now().isoformat(),
        'files': exported_files,
        'blend_file': bpy.data.filepath or "unsaved",
        'format': scene_props.export_format,
        'scope': scene_props.export_scope,
        'mode': scene_props.export_mode,
        'export_path': export_path
    }
    
    if 'history' not in track_data[settings_key]:
        track_data[settings_key]['history'] = []
    
    track_data[settings_key]['history'].append({
        'timestamp': datetime.datetime.now().isoformat(),
        'files': exported_files,
        'format': scene_props.export_format,
        'scope': scene_props.export_scope,
        'mode': scene_props.export_mode
    })
    
    # Keep only last 10 history entries
    track_data[settings_key]['history'] = track_data[settings_key]['history'][-10:]
    
    save_track_data(track_data)

def find_orphaned_files():
    """Enhanced orphan detection that considers export settings changes"""
    track_data = load_track_data()
    orphans = []
    
    # Get all currently tracked files across all export settings
    all_tracked_files = set()
    current_export_paths = set()
    
    for settings_key, path_data in track_data.items():
        if 'last_export' in path_data:
            all_tracked_files.update(path_data['last_export']['files'])
            # Extract export path from settings key
            export_path = path_data['last_export'].get('export_path', settings_key.split('|')[0])
            current_export_paths.add(export_path)
    
    # Check all current export paths for orphaned files
    for export_path in current_export_paths:
        if not os.path.exists(export_path):
            continue
            
        # Get all files in export directory and subdirectories
        current_files = set()
        supported_extensions = {'.glb', '.gltf', '.obj', '.fbx', '.bin'}
        
        for root, dirs, files in os.walk(export_path):
            # Skip track files themselves
            if root.endswith('.export.track'):
                continue
                
            for file in files:
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext in supported_extensions:
                    full_path = os.path.join(root, file)
                    current_files.add(full_path)
        
        # Find files that exist but aren't tracked
        for file_path in current_files:
            if file_path not in all_tracked_files:
                orphans.append(file_path)
    
    return orphans

def cleanup_orphaned_files(cleanup_empty_folders=False):
    """Enhanced cleanup with optional empty folder removal"""
    orphans = find_orphaned_files()
    deleted_files = []
    deleted_folders = []
    
    for orphan in orphans:
        try:
            base_name = os.path.splitext(orphan)[0]
            parent_dir = os.path.dirname(orphan)
            
            os.remove(orphan)
            deleted_files.append(orphan)
            print(f"🗑️ Deleted orphaned file: {orphan}")
            
            # Clean up associated files
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
    
    # NEW: Optional empty folder cleanup
    if cleanup_empty_folders:
        deleted_folders = cleanup_empty_folders_func()
    
    # Update track data to remove references to deleted files
    track_data = load_track_data()
    for settings_key, path_data in track_data.items():
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
    
    if cleanup_empty_folders and deleted_folders:
        print(f"🗑️ Deleted {len(deleted_folders)} empty folders")
    
    return deleted_files

def cleanup_empty_folders_func():
    """Remove empty folders from export directories"""
    deleted_folders = []
    track_data = load_track_data()
    
    # Get all export paths from track data
    export_paths = set()
    for settings_key, path_data in track_data.items():
        if 'last_export' in path_data:
            export_path = path_data['last_export'].get('export_path', settings_key.split('|')[0])
            if os.path.exists(export_path):
                export_paths.add(export_path)
    
    for export_path in export_paths:
        # Walk through all subdirectories and remove empty ones
        for root, dirs, files in os.walk(export_path, topdown=False):
            # Skip if this is the root export path
            if root == export_path:
                continue
                
            # Check if directory is empty (no files and no subdirectories)
            if not os.listdir(root):
                try:
                    os.rmdir(root)
                    deleted_folders.append(root)
                    print(f"🗑️ Deleted empty folder: {root}")
                except Exception as e:
                    print(f"❌ Failed to delete empty folder {root}: {str(e)}")
    
    return deleted_folders

# ===== UTILITY FUNCTIONS =====
def get_selected_items(context):
    """Get selected objects and collections - FULLY COMPATIBLE VERSION"""
    return get_selected_ids_compat(context)

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
    """Check if an operator exists - COMPATIBLE VERSION"""
    try:
        op_name = operator_name.split('.')[-1]
        return hasattr(bpy.ops, op_name)
    except:
        return False

def get_available_export_operators():
    """Get available export operators - COMPATIBLE VERSION"""
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
    Export OBJ files with full Blender version compatibility
    """
    try:
        scene_props = bpy.context.scene.advanced_glb_props
        
        if is_blender_version_or_newer(4, 0):
            # Blender 4.0+ uses wm.obj_export
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
            # Blender 2.8-3.x uses export_scene.obj
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
    
    # Extract -dir modifier first (only use the first one found)
    dir_match = re.search(r'\s*-dir:([^\s]+)\s*', clean_name)
    if dir_match:
        modifiers['dir'] = dir_match.group(1).strip()
        clean_name = clean_name.replace(dir_match.group(0), ' ').strip()
    
    # Count occurrences of each modifier
    sk_count = len(re.findall(r'\s*-sk\s*', clean_name))
    dk_count = len(re.findall(r'\s*-dk\s*', clean_name))
    sep_count = len(re.findall(r'\s*-sep\s*', clean_name))
    anim_count = len(re.findall(r'\s*-anim\s*', clean_name))
    
    # Set flags based on presence (any count > 0)
    modifiers['sep'] = sep_count > 0
    modifiers['dk'] = dk_count > 0  
    modifiers['sk'] = sk_count > 0
    modifiers['anim'] = anim_count > 0
    
    # Remove all modifier instances from the clean name
    clean_name = re.sub(r'\s*-sep\s*', ' ', clean_name).strip()
    clean_name = re.sub(r'\s*-dk\s*', ' ', clean_name).strip()
    clean_name = re.sub(r'\s*-sk\s*', ' ', clean_name).strip()
    clean_name = re.sub(r'\s*-anim\s*', ' ', clean_name).strip()
    
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
    
    return clean_name, modifiers

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

def move_to_3d_cursor(obj, cursor_location):
    """Move object to 3D cursor while preserving its local transform"""
    world_matrix = obj.matrix_world.copy()
    offset = cursor_location - world_matrix.to_translation()
    obj.matrix_world.translation = world_matrix.translation + offset

def restore_original_position(obj, original_matrix):
    """Restore object to its original position"""
    obj.matrix_world = original_matrix

def safe_apply_modifiers(obj):
    """Safely apply all modifiers to an object, skipping any that fail - COMPATIBLE VERSION"""
    success_count = 0
    error_count = 0
    
    # Store current selection and active object
    original_active = bpy.context.view_layer.objects.active
    original_selection = bpy.context.selected_objects
    
    # Use compatibility wrapper for context operations
    with temp_override_compat(object=obj):
        # Use a while loop to safely apply modifiers as the list changes
        while obj.modifiers:
            modifier = obj.modifiers[0]
            modifier_name = modifier.name
            
            try:
                # Select only this object and make it active
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj
                
                # Apply the modifier
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
    
    # Restore original selection
    bpy.ops.object.select_all(action='DESELECT')
    for obj_orig in original_selection:
        obj_orig.select_set(True)
    bpy.context.view_layer.objects.active = original_active
    
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
                    # GLTF/GLB export with version compatibility
                    export_params = {
                        'filepath': export_path,
                        'export_format': 'GLB' if scene_props.export_format == 'GLB' else 'GLTF_SEPARATE',
                        'use_selection': True,
                        'export_apply': False,  # Already applied above if needed
                        'export_animations': scene_props.apply_animations,
                    }
                    
                    # Add version-specific parameters
                    if is_blender_version_or_newer(3, 0):
                        export_params['export_yup'] = (scene_props.export_up_axis == 'Y')
                    else:
                        # Blender 2.8 uses slightly different parameter names
                        export_params['yup'] = (scene_props.export_up_axis == 'Y')
                    
                    bpy.ops.export_scene.gltf(**export_params)
                    
                elif scene_props.export_format == 'OBJ':
                    success = export_obj_compat(
                        filepath=export_path,
                        use_selection=True,
                        apply_modifiers=False  # Already applied above if needed
                    )
                    if not success:
                        continue
                elif scene_props.export_format == 'FBX':
                    # FBX export with version compatibility
                    export_params = {
                        'filepath': export_path,
                        'use_selection': True,
                        'use_mesh_modifiers': False,  # Already applied above if needed
                        'bake_anim': scene_props.apply_animations,
                        'axis_forward': 'Y',
                        'axis_up': 'Z' if scene_props.export_up_axis == 'Z' else 'Y'
                    }
                    
                    bpy.ops.export_scene.fbx(**export_params)
                
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
                    # GLTF/GLB export with version compatibility
                    export_params = {
                        'filepath': export_path,
                        'export_format': 'GLB' if scene_props.export_format == 'GLB' else 'GLTF_SEPARATE',
                        'use_selection': True,
                        'export_apply': False,
                        'export_animations': scene_props.apply_animations,
                    }
                    
                    if is_blender_version_or_newer(3, 0):
                        export_params['export_yup'] = (scene_props.export_up_axis == 'Y')
                    else:
                        export_params['yup'] = (scene_props.export_up_axis == 'Y')
                    
                    bpy.ops.export_scene.gltf(**export_params)
                    
                elif scene_props.export_format == 'OBJ':
                    success = export_obj_compat(
                        filepath=export_path,
                        use_selection=True,
                        apply_modifiers=False
                    )
                    if not success:
                        continue
                elif scene_props.export_format == 'FBX':
                    export_params = {
                        'filepath': export_path,
                        'use_selection': True,
                        'use_mesh_modifiers': False,
                        'bake_anim': scene_props.apply_animations,
                        'axis_forward': 'Y',
                        'axis_up': 'Z' if scene_props.export_up_axis == 'Z' else 'Y'
                    }
                    
                    bpy.ops.export_scene.fbx(**export_params)
                
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
    """Main export function with full version compatibility"""
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
                    # GLTF/GLB export with version compatibility
                    export_params = {
                        'filepath': export_path,
                        'export_format': 'GLB' if scene_props.export_format == 'GLB' else 'GLTF_SEPARATE',
                        'use_selection': False,
                        'export_apply': prefs.apply_modifiers,
                        'export_animations': scene_props.apply_animations,
                    }
                    
                    if is_blender_version_or_newer(3, 0):
                        export_params['export_yup'] = (scene_props.export_up_axis == 'Y')
                    else:
                        export_params['yup'] = (scene_props.export_up_axis == 'Y')
                    
                    bpy.ops.export_scene.gltf(**export_params)
                    
                elif scene_props.export_format == 'OBJ':
                    success = export_obj_compat(
                        filepath=export_path,
                        use_selection=False,
                        apply_modifiers=prefs.apply_modifiers
                    )
                    if not success:
                        return {'CANCELLED'}
                elif scene_props.export_format == 'FBX':
                    export_params = {
                        'filepath': export_path,
                        'use_selection': False,
                        'use_mesh_modifiers': prefs.apply_modifiers,
                        'bake_anim': scene_props.apply_animations,
                        'axis_forward': 'Y',
                        'axis_up': 'Z' if scene_props.export_up_axis == 'Z' else 'Y'
                    }
                    
                    bpy.ops.export_scene.fbx(**export_params)
                
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
                        export_params = {
                            'filepath': export_path,
                            'export_format': 'GLB' if scene_props.export_format == 'GLB' else 'GLTF_SEPARATE',
                            'use_selection': True,
                            'export_apply': prefs.apply_modifiers,
                            'export_animations': scene_props.apply_animations,
                        }
                        
                        if is_blender_version_or_newer(3, 0):
                            export_params['export_yup'] = (scene_props.export_up_axis == 'Y')
                        else:
                            export_params['yup'] = (scene_props.export_up_axis == 'Y')
                        
                        bpy.ops.export_scene.gltf(**export_params)
                        
                    elif scene_props.export_format == 'OBJ':
                        success = export_obj_compat(
                            filepath=export_path,
                            use_selection=True,
                            apply_modifiers=prefs.apply_modifiers
                        )
                        if not success:
                            continue
                    elif scene_props.export_format == 'FBX':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers,
                            'bake_anim': scene_props.apply_animations,
                            'axis_forward': 'Y',
                            'axis_up': 'Z' if scene_props.export_up_axis == 'Z' else 'Y'
                        }
                        
                        bpy.ops.export_scene.fbx(**export_params)
                    
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
                        export_params = {
                            'filepath': export_path,
                            'export_format': 'GLB' if scene_props.export_format == 'GLB' else 'GLTF_SEPARATE',
                            'use_selection': True,
                            'export_apply': prefs.apply_modifiers,
                            'export_animations': scene_props.apply_animations,
                        }
                        
                        if is_blender_version_or_newer(3, 0):
                            export_params['export_yup'] = (scene_props.export_up_axis == 'Y')
                        else:
                            export_params['yup'] = (scene_props.export_up_axis == 'Y')
                        
                        bpy.ops.export_scene.gltf(**export_params)
                        
                    elif scene_props.export_format == 'OBJ':
                        success = export_obj_compat(
                            filepath=export_path,
                            use_selection=True,
                            apply_modifiers=prefs.apply_modifiers
                        )
                        if not success:
                            continue
                    elif scene_props.export_format == 'FBX':
                        export_params = {
                            'filepath': export_path,
                            'use_selection': True,
                            'use_mesh_modifiers': prefs.apply_modifiers,
                            'bake_anim': scene_props.apply_animations,
                            'axis_forward': 'Y',
                            'axis_up': 'Z' if scene_props.export_up_axis == 'Z' else 'Y'
                        }
                        
                        bpy.ops.export_scene.fbx(**export_params)
                    
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
    bpy.utils.register_class(ADVANCED_GLB_OT_highlight_exportable)
    bpy.utils.register_class(ADVANCED_GLB_OT_delete_track_file)
    bpy.utils.register_class(ADVANCED_GLB_OT_execute_order_66)
    bpy.utils.register_class(ADVANCED_GLB_OT_validate_export_modifiers)
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
    bpy.utils.unregister_class(ADVANCED_GLB_OT_highlight_exportable)
    bpy.utils.unregister_class(ADVANCED_GLB_OT_delete_track_file)
    bpy.utils.unregister_class(ADVANCED_GLB_OT_execute_order_66)
    bpy.utils.unregister_class(ADVANCED_GLB_OT_validate_export_modifiers)
    bpy.utils.unregister_class(ADVANCED_GLB_PT_panel)
    bpy.utils.unregister_class(AdvancedGLBPreferences)
    bpy.utils.unregister_class(AdvancedGLBSceneProperties)
    
    del bpy.types.Scene.advanced_glb_props
    
    if on_save_handler in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(on_save_handler)

if __name__ == "__main__":
    register()
