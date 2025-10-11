bl_info = {
    "name": "Advanced GLB Auto-Exporter",
    "author": "WildStar Studios",
    "version": (2, 0),
    "blender": (4, 4, 0),
    "location": "View3D > Sidebar > GLB Export",
    "description": "Advanced GLB export with proper origin handling",
    "category": "Import-Export",
}

import bpy
import os
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
                full_path = os.path.join(scene_props.export_path, f"{scene_props.scene_export_filename}.glb")
                essential_box.label(text=f"→ {os.path.basename(full_path)}", icon='FILE_BLEND')
        
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

def get_quick_summary(scene_props, prefs):
    """Generate quick summary of what will be exported"""
    summary_lines = []
    
    if scene_props.export_scope == 'SCENE':
        objects_to_export = [obj for obj in bpy.data.objects if should_export_object(obj)]
        summary_lines.append(f"📦 Exporting {len(objects_to_export)} objects as single file")
        
    elif scene_props.export_scope == 'COLLECTION':
        export_roots = find_collection_export_roots(bpy.context.scene.collection)
        object_count = sum(
            len([obj for obj in col.all_objects if should_export_object(obj)])
            for root_col, collections in export_roots.items()
            for col in collections
        )
        summary_lines.append(f"📦 Exporting {len(export_roots)} collections")
        summary_lines.append(f"📊 Total objects: {object_count}")
        
        if prefs.export_individual_origins:
            summary_lines.append("📍 Each collection at local origin")
        
    elif scene_props.export_scope == 'OBJECT':
        objects_to_export = [obj for obj in bpy.data.objects if should_export_object(obj)]
        summary_lines.append(f"📦 Exporting {len(objects_to_export)} objects")
        
        if prefs.export_individual_origins:
            summary_lines.append("📍 Each object at local origin")
    
    return summary_lines

def get_detailed_summary(scene_props, prefs):
    """Generate detailed summary of what will be exported"""
    summary_lines = []
    
    if scene_props.export_scope == 'SCENE':
        objects_to_export = [obj for obj in bpy.data.objects if should_export_object(obj)]
        summary_lines.append(f"Scene Export: {len(objects_to_export)} objects")
        summary_lines.append(f"File: {scene_props.scene_export_filename}.glb")
        
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
            object_count = sum(len([obj for obj in col.all_objects if should_export_object(obj)]) 
                             for col in collections_in_root)
            
            collection_list = " + ".join([col.name for col in collections_in_root])
            summary_lines.append(f"\n• {root_collection.name}.glb: {object_count} objects")
            
            if len(collections_in_root) > 1:
                summary_lines.append(f"  Includes: {collection_list}")
            
            if prefs.show_hidden_objects:
                for col in collections_in_root:
                    objects_in_col = [obj for obj in col.all_objects if should_export_object(obj)]
                    if objects_in_col:
                        summary_lines.append(f"  {col.name}:")
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
            summary_lines.append(f"• {obj.name}.glb ({obj.type})")
        
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
        # Skip collections that shouldn't be exported (-dk collections)
        if not should_export_collection(collection):
            return
        
        # If this collection has -sep, it becomes a new export root
        if is_separate_export_collection(collection):
            current_root = collection
            if collection not in export_roots:
                export_roots[collection] = []
        
        # If we don't have a current root yet, this collection becomes the root
        if current_root is None:
            current_root = collection
            if collection not in export_roots:
                export_roots[collection] = []
        
        # Add this collection to the current root
        if current_root is not None and collection not in export_roots[current_root]:
            export_roots[current_root].append(collection)
        
        # Recursively traverse child collections
        for child_collection in collection.children:
            traverse_collections(child_collection, current_root)
    
    # Start traversal from scene collection children
    for child_collection in scene_collection.children:
        traverse_collections(child_collection)
    
    return export_roots

def is_separate_export_collection(collection):
    """Check if a collection should be exported separately (has -sep suffix)"""
    return "-sep" in collection.name

def get_object_exclusion_reason(obj):
    """Get reason why an object is excluded from export"""
    reasons = []
    if "-dk" in obj.name:
        reasons.append("'-dk' in name")
    if obj.hide_viewport:
        reasons.append("hidden in viewport")
    if obj.hide_render:
        reasons.append("hidden in renders")
    if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'ARMATURE'}:
        reasons.append("non-exportable type")
    return ", ".join(reasons) or "unknown reason"

def get_collection_exclusion_reason(col):
    """Get reason why a collection is excluded from export"""
    reasons = []
    if "-dk" in col.name:
        reasons.append("'-dk' in name")
    if col.hide_viewport:
        reasons.append("hidden in viewport")
    if col.hide_render:
        reasons.append("hidden in renders")
    return ", ".join(reasons) or "unknown reason"

def should_export_object(obj):
    """Determine if an object should be exported"""
    # Skip objects with "-dk" in name
    if "-dk" in obj.name:
        return False
    
    # Skip hidden objects
    if obj.hide_viewport or obj.hide_render:
        return False
    
    # Skip non-exportable types
    if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT', 'ARMATURE'}:
        return False
    
    return True

def should_export_collection(col):
    """Determine if a collection should be exported"""
    # Skip collections with "-dk" in name
    if "-dk" in col.name:
        return False
    
    # Skip hidden collections
    if col.hide_viewport or col.hide_render:
        return False
    
    return True

def move_to_3d_cursor(obj, cursor_location):
    """Move object to 3D cursor while preserving its local transform"""
    # Store the object's current world matrix
    world_matrix = obj.matrix_world.copy()
    
    # Calculate the offset from object's origin to 3D cursor
    offset = cursor_location - world_matrix.to_translation()
    
    # Apply the offset to the object's location
    obj.location = obj.location + offset

def restore_original_position(obj, original_matrix):
    """Restore object to its original position"""
    obj.matrix_world = original_matrix

def export_glb(context):
    scene_props = context.scene.advanced_glb_props
    prefs = context.preferences.addons[__name__].preferences
    
    # Check if export path is set
    if not scene_props.export_path:
        print("Export failed: No export directory specified")
        return {'CANCELLED'}
    
    # Ensure directory exists
    if not os.path.exists(scene_props.export_path):
        os.makedirs(scene_props.export_path)
    
    # Store original positions for restoration
    original_positions = {}
    cursor_location = bpy.context.scene.cursor.location.copy()
    
    try:
        # Handle individual origins if requested (disabled for scene export)
        if prefs.export_individual_origins and scene_props.export_scope != 'SCENE':
            print("📍 Using local origins - moving objects to 3D cursor...")
            
            if scene_props.export_scope == 'COLLECTION':
                # Move each collection's objects as a group to maintain relative positions
                export_roots = find_collection_export_roots(bpy.context.scene.collection)
                for root_collection, collections_in_root in export_roots.items():
                    # Find all objects in this export root
                    objects_in_root = []
                    for col in collections_in_root:
                        objects_in_root.extend([obj for obj in col.all_objects if should_export_object(obj)])
                    
                    if objects_in_root:
                        # Store original positions
                        for obj in objects_in_root:
                            original_positions[obj] = obj.matrix_world.copy()
                        
                        # Move entire group to 3D cursor
                        for obj in objects_in_root:
                            move_to_3d_cursor(obj, cursor_location)
            
            elif scene_props.export_scope == 'OBJECT':
                # Move each object individually to 3D cursor
                for obj in bpy.data.objects:
                    if should_export_object(obj):
                        original_positions[obj] = obj.matrix_world.copy()
                        move_to_3d_cursor(obj, cursor_location)
        
        # Set common export settings
        export_settings = {
            'export_format': 'GLB',
            'export_apply': prefs.apply_modifiers,
            'export_yup': True
        }
        
        # Handle export scope
        if scene_props.export_scope == 'SCENE':
            # Export entire scene as single file
            export_path = os.path.join(scene_props.export_path, f"{scene_props.scene_export_filename}.glb")
            export_settings['filepath'] = export_path
            export_settings['use_selection'] = False
            
            try:
                # Deselect all, then select exportable objects
                bpy.ops.object.select_all(action='DESELECT')
                for obj in bpy.data.objects:
                    if should_export_object(obj):
                        obj.select_set(True)
                
                bpy.ops.export_scene.gltf(**export_settings)
                print(f"✅ Exported scene to: {export_path}")
                return {'FINISHED'}
            except Exception as e:
                print(f"❌ Scene export failed: {str(e)}")
                return {'CANCELLED'}
        
        elif scene_props.export_scope == 'COLLECTION':
            # Export each collection export root individually
            export_roots = find_collection_export_roots(bpy.context.scene.collection)
            success_count = 0
            
            for root_collection, collections_in_root in export_roots.items():
                # Use collection name for filename
                filename = f"{root_collection.name}.glb"
                export_path = os.path.join(scene_props.export_path, filename)
                
                # Select all objects from all collections in this export root
                bpy.ops.object.select_all(action='DESELECT')
                object_count = 0
                
                for col in collections_in_root:
                    for obj in col.all_objects:
                        if should_export_object(obj):
                            obj.select_set(True)
                            object_count += 1
                
                if object_count == 0:
                    print(f"⚠️ Skipping '{root_collection.name}': No exportable objects")
                    continue
                
                # Update export settings
                root_settings = export_settings.copy()
                root_settings['filepath'] = export_path
                root_settings['use_selection'] = True
                
                try:
                    bpy.ops.export_scene.gltf(**root_settings)
                    collection_list = ", ".join([col.name for col in collections_in_root])
                    print(f"✅ Exported '{root_collection.name}' to: {export_path}")
                    print(f"   Contains {object_count} objects from: {collection_list}")
                    success_count += 1
                except Exception as e:
                    print(f"❌ Collection export failed for '{root_collection.name}': {str(e)}")
            
            return {'FINISHED'} if success_count > 0 else {'CANCELLED'}
        
        elif scene_props.export_scope == 'OBJECT':
            # Export each object individually
            success_count = 0
            
            for obj in bpy.data.objects:
                if not should_export_object(obj):
                    continue
                
                # Use object name for filename
                filename = f"{obj.name}.glb"
                export_path = os.path.join(scene_props.export_path, filename)
                
                # Select only this object
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                
                # Update export settings
                object_settings = export_settings.copy()
                object_settings['filepath'] = export_path
                object_settings['use_selection'] = True
                
                try:
                    bpy.ops.export_scene.gltf(**object_settings)
                    print(f"✅ Exported '{obj.name}' to: {export_path}")
                    success_count += 1
                except Exception as e:
                    print(f"❌ Object export failed for '{obj.name}': {str(e)}")
            
            return {'FINISHED'} if success_count > 0 else {'CANCELLED'}
        
        return {'CANCELLED'}
    
    finally:
        # Always restore original positions if we moved objects
        if original_positions:
            print("📍 Restoring original object positions...")
            for obj, original_matrix in original_positions.items():
                if obj:  # Ensure object still exists
                    restore_original_position(obj, original_matrix)

@persistent
def on_save_handler(dummy):
    if not bpy.context.preferences.addons.get(__name__):
        return
    
    scene_props = bpy.context.scene.advanced_glb_props
    if not scene_props.auto_export_on_save:
        return
    
    # Skip if export path isn't set
    if not scene_props.export_path:
        print("Auto-export skipped: Export directory not configured")
        return
    
    export_glb(bpy.context)

def register():
    bpy.utils.register_class(ADVANCED_GLB_OT_export)
    bpy.utils.register_class(ADVANCED_GLB_PT_panel)
    bpy.utils.register_class(AdvancedGLBPreferences)
    bpy.utils.register_class(AdvancedGLBSceneProperties)
    
    # Add scene properties
    bpy.types.Scene.advanced_glb_props = bpy.props.PointerProperty(type=AdvancedGLBSceneProperties)
    
    # Add save handler
    if on_save_handler not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(on_save_handler)

def unregister():
    bpy.utils.unregister_class(ADVANCED_GLB_OT_export)
    bpy.utils.unregister_class(ADVANCED_GLB_PT_panel)
    bpy.utils.unregister_class(AdvancedGLBPreferences)
    bpy.utils.unregister_class(AdvancedGLBSceneProperties)
    
    # Remove scene properties
    del bpy.types.Scene.advanced_glb_props
    
    # Remove save handler
    if on_save_handler in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(on_save_handler)

if __name__ == "__main__":

    register()
