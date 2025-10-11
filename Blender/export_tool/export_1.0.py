bl_info = {
    "name": "Advanced GLB Auto-Exporter",
    "author": "WildStar Studios",
    "version": (1, 0),
    "blender": (4, 3, 0),
    "location": "View3D > Sidebar > GLB Export",
    "description": "Advanced GLB export with detailed object listing",
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
            prefs = context.preferences.addons[__name__].preferences
            if prefs.export_scope == 'SCENE':
                self.report({'INFO'}, f"Exported scene to {prefs.export_path}")
            else:
                self.report({'INFO'}, f"Exported {prefs.export_scope.lower()} to {prefs.export_path}")
        return result

class ADVANCED_GLB_PT_panel(bpy.types.Panel):
    bl_label = "GLB Auto-Export"
    bl_idname = "VIEW3D_PT_advanced_glb_export"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'GLB Export'

    def draw(self, context):
        layout = self.layout
        prefs = context.preferences.addons[__name__].preferences
        
        # Export path
        layout.prop(prefs, "export_path")
        
        # Auto-export toggle
        layout.prop(prefs, "auto_export_on_save", text="Enable Auto-Export on Save")
        
        # Export settings box
        box = layout.box()
        box.label(text="Export Settings:")
        box.prop(prefs, "export_individual_origins")
        box.prop(prefs, "apply_modifiers")
        
        # Export scope selection
        box.prop(prefs, "export_scope", text="Export Scope")
        
        # Detailed listing options
        list_box = layout.box()
        list_box.prop(prefs, "show_detailed_list", text="Show Detailed List")
        
        if prefs.show_detailed_list:
            list_box.prop(prefs, "show_hidden_objects", text="Show Hidden Objects")
        
        # Summary of what will be exported
        summary_box = layout.box()
        summary_box.label(text="Export Summary:")
        
        # Get and display detailed summary
        summary_lines = get_export_summary(prefs)
        for line in summary_lines:
            summary_box.label(text=line)
        
        # Export button
        layout.operator("export.advanced_glb", icon='EXPORT')

class AdvancedGLBPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    export_path: StringProperty(
        name="Export Path",
        subtype='FILE_PATH',
        default=os.path.join(os.path.expanduser("~"), "export.glb"),
        description="Default path for GLB exports"
    )
    
    auto_export_on_save: BoolProperty(
        name="Auto Export on Save",
        default=True,
        description="Automatically export GLB when saving the Blender file"
    )
    
    export_individual_origins: BoolProperty(
        name="Export by Individual Origins",
        default=False,
        description="Export each object with its own origin point at (0,0,0)"
    )
    
    apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        default=True,
        description="Apply modifiers before export"
    )
    
    export_scope: EnumProperty(
        name="Export Scope",
        items=[
            ('SCENE', "Scene", "Export entire scene"),
            ('COLLECTION', "Collection", "Export collections individually"),
            ('OBJECT', "Object", "Export objects individually"),
        ],
        default='SCENE',
        description="Select what to export"
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

def get_export_summary(prefs):
    """Generate detailed summary of what will be exported"""
    summary_lines = []
    
    # Get collections to export
    root_collections = []
    if prefs.export_scope == 'COLLECTION':
        for col in bpy.context.scene.collection.children:
            if should_export_collection(col):
                root_collections.append(col)
    else:
        # For scene and object exports, include all collections for context
        root_collections = list(bpy.context.scene.collection.children)
    
    # Get objects to export
    objects_to_export = []
    if prefs.export_scope == 'SCENE':
        objects_to_export = [obj for obj in bpy.data.objects if should_export_object(obj)]
    elif prefs.export_scope == 'OBJECT':
        objects_to_export = [obj for obj in bpy.data.objects if should_export_object(obj)]
    
    # Create summary based on export scope
    if prefs.export_scope == 'SCENE':
        if not prefs.show_detailed_list:
            summary_lines.append(f"Scene: {len(objects_to_export)} objects")
        else:
            summary_lines.append("Scene Objects to Export:")
            for obj in objects_to_export:
                summary_lines.append(f"  - {obj.name} ({obj.type})")
            
            if prefs.show_hidden_objects:
                hidden_objects = [obj for obj in bpy.data.objects if not should_export_object(obj)]
                if hidden_objects:
                    summary_lines.append("\nHidden Objects (Not Exported):")
                    for obj in hidden_objects:
                        collection_names = ", ".join([col.name for col in get_object_collections(obj)])
                        summary_lines.append(f"  - {obj.name} ({obj.type}) in {collection_names}")
    
    elif prefs.export_scope == 'COLLECTION':
        if not prefs.show_detailed_list:
            summary_lines.append(f"{len(root_collections)} root collections")
        else:
            summary_lines.append("Collections to Export:")
            for col in root_collections:
                exportable_objs = [obj for obj in col.all_objects if should_export_object(obj)]
                hidden_objs = [obj for obj in col.all_objects if not should_export_object(obj)]
                
                # Collection status
                status = " (Hidden Collection)" if col.hide_viewport or col.hide_render else ""
                
                if prefs.show_hidden_objects or not status:
                    summary_lines.append(f"\nCollection '{col.name}'{status}:")
                    summary_lines.append(f"  - Objects: {len(exportable_objs)} exportable")
                    
                    if prefs.show_hidden_objects and hidden_objs:
                        summary_lines.append(f"  - Hidden: {len(hidden_objs)} objects")
                    
                    # List objects if requested
                    if prefs.show_hidden_objects:
                        summary_lines.append("\n  Objects in Collection:")
                        for obj in col.all_objects:
                            status = " (Hidden)" if not should_export_object(obj) else ""
                            summary_lines.append(f"    - {obj.name}{status}")
    
    elif prefs.export_scope == 'OBJECT':
        if not prefs.show_detailed_list:
            summary_lines.append(f"{len(objects_to_export)} objects")
        else:
            summary_lines.append("Objects to Export:")
            for obj in objects_to_export:
                collection_names = ", ".join([col.name for col in get_object_collections(obj)])
                summary_lines.append(f"  - {obj.name} ({obj.type}) in {collection_names}")
            
            if prefs.show_hidden_objects:
                hidden_objects = [obj for obj in bpy.data.objects if not should_export_object(obj)]
                if hidden_objects:
                    summary_lines.append("\nHidden Objects (Not Exported):")
                    for obj in hidden_objects:
                        collection_names = ", ".join([col.name for col in get_object_collections(obj)])
                        reason = get_exclusion_reason(obj)
                        summary_lines.append(f"  - {obj.name} ({obj.type}) in {collection_names} - {reason}")
    
    # Add counts if detailed list is empty
    if not summary_lines:
        if prefs.export_scope == 'SCENE':
            obj_count = sum(1 for obj in bpy.data.objects if should_export_object(obj))
            summary_lines.append(f"Scene: {obj_count} objects")
        elif prefs.export_scope == 'COLLECTION':
            root_collections = [col for col in bpy.context.scene.collection.children 
                               if should_export_collection(col)]
            summary_lines.append(f"{len(root_collections)} root collections")
        elif prefs.export_scope == 'OBJECT':
            obj_count = sum(1 for obj in bpy.data.objects if should_export_object(obj))
            summary_lines.append(f"{obj_count} objects")
    
    return summary_lines

def get_object_collections(obj):
    """Get all collections an object belongs to"""
    return [col for col in bpy.data.collections if obj.name in col.objects]

def get_exclusion_reason(obj):
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

def should_export_object(obj):
    """Determine if an object should be exported"""
    # Skip objects with "-dk" in name
    if "-dk" in obj.name:
        return False
    
    # Skip hidden objects (used for modifiers/references)
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

def reset_origins(original_transforms):
    """Restore original object transforms after export"""
    for obj, (loc, rot, scale) in original_transforms.items():
        if obj:  # Ensure object still exists
            obj.location = loc
            obj.rotation_euler = rot
            obj.scale = scale

def move_to_origin(obj):
    """Move object to world origin while preserving mesh relationships"""
    if obj.parent is None:
        # Root object - simply move to origin
        obj.location = (0, 0, 0)
        obj.rotation_euler = (0, 0, 0)
        obj.scale = (1, 1, 1)
    else:
        # Parented object - adjust local matrix
        obj.matrix_local = mathutils.Matrix.Identity(4)

def export_glb(context):
    prefs = context.preferences.addons[__name__].preferences
    path = prefs.export_path
    
    if not path:
        print("Auto-export failed: No export path specified")
        return {'CANCELLED'}
    
    # Ensure directory exists
    dirname = os.path.dirname(path)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname)
    
    # Ensure .glb extension
    if not path.lower().endswith('.glb'):
        path += '.glb'
    
    # Store original transforms for restoration
    original_transforms = {}
    objects_to_export = []
    
    try:
        # Handle individual origins if requested
        if prefs.export_individual_origins:
            # Collect objects to export
            if prefs.export_scope == 'SCENE':
                objects_to_export = [obj for obj in bpy.data.objects 
                                    if should_export_object(obj)]
            elif prefs.export_scope == 'COLLECTION':
                for collection in bpy.context.scene.collection.children:
                    if should_export_collection(collection):
                        objects_to_export.extend([obj for obj in collection.all_objects 
                                                if should_export_object(obj)])
            elif prefs.export_scope == 'OBJECT':
                objects_to_export = [obj for obj in bpy.data.objects 
                                    if should_export_object(obj)]
            
            # Store original transforms and move to origin
            for obj in objects_to_export:
                original_transforms[obj] = (
                    obj.location.copy(),
                    obj.rotation_euler.copy(),
                    obj.scale.copy()
                )
                move_to_origin(obj)
        
        # Set common export settings
        export_settings = {
            'filepath': path,
            'export_format': 'GLB',
            'export_apply': prefs.apply_modifiers,
            'export_yup': True
        }
        
        # Handle export scope
        if prefs.export_scope == 'SCENE':
            # Export entire scene, excluding hidden and "-dk" objects
            export_settings['use_selection'] = False
            try:
                # First deselect all objects
                bpy.ops.object.select_all(action='DESELECT')
                
                # Select only objects that should be exported
                for obj in bpy.data.objects:
                    if should_export_object(obj):
                        obj.select_set(True)
                
                # Perform export
                bpy.ops.export_scene.gltf(**export_settings)
                print(f"Exported scene to: {path}")
                return {'FINISHED'}
            except Exception as e:
                print(f"Scene export failed: {str(e)}")
                return {'CANCELLED'}
        
        elif prefs.export_scope == 'COLLECTION':
            # Export each root collection individually
            success_count = 0
            for collection in bpy.context.scene.collection.children:
                if not should_export_collection(collection):
                    continue  # Skip collections marked to exclude
                    
                # Create path for this collection
                collection_path = os.path.join(
                    os.path.dirname(path),
                    f"{os.path.splitext(os.path.basename(path))[0]}_{collection.name}.glb"
                )
                
                # Select only objects in this collection
                bpy.ops.object.select_all(action='DESELECT')
                for obj in collection.all_objects:
                    if should_export_object(obj):  # Skip objects marked to exclude
                        obj.select_set(True)
                
                # Update export settings for this collection
                collection_settings = export_settings.copy()
                collection_settings['filepath'] = collection_path
                collection_settings['use_selection'] = True
                
                try:
                    bpy.ops.export_scene.gltf(**collection_settings)
                    print(f"Exported collection '{collection.name}' to: {collection_path}")
                    success_count += 1
                except Exception as e:
                    print(f"Collection export failed for '{collection.name}': {str(e)}")
            
            return {'FINISHED'} if success_count > 0 else {'CANCELLED'}
        
        elif prefs.export_scope == 'OBJECT':
            # Export each object individually
            success_count = 0
            for obj in bpy.data.objects:
                if not should_export_object(obj):
                    continue
                    
                # Create path for this object
                object_path = os.path.join(
                    os.path.dirname(path),
                    f"{os.path.splitext(os.path.basename(path))[0]}_{obj.name}.glb"
                )
                
                # Select only this object
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                
                # Update export settings for this object
                object_settings = export_settings.copy()
                object_settings['filepath'] = object_path
                object_settings['use_selection'] = True
                
                try:
                    bpy.ops.export_scene.gltf(**object_settings)
                    print(f"Exported object '{obj.name}' to: {object_path}")
                    success_count += 1
                except Exception as e:
                    print(f"Object export failed for '{obj.name}': {str(e)}")
            
            return {'FINISHED'} if success_count > 0 else {'CANCELLED'}
        
        return {'CANCELLED'}
    
    finally:
        # Always restore original transforms if we modified them
        if prefs.export_individual_origins and original_transforms:
            reset_origins(original_transforms)

@persistent
def on_save_handler(dummy):
    if not bpy.context.preferences.addons.get(__name__):
        return
    
    prefs = bpy.context.preferences.addons[__name__].preferences
    if not prefs.auto_export_on_save:
        return
    
    # Skip unsaved files
    if not bpy.data.filepath:
        print("Auto-export skipped: Save your file first")
        return
    
    # Skip if export path isn't set
    if not prefs.export_path:
        print("Auto-export skipped: Export path not configured")
        return
    
    export_glb(bpy.context)

def register():
    bpy.utils.register_class(ADVANCED_GLB_OT_export)
    bpy.utils.register_class(ADVANCED_GLB_PT_panel)
    bpy.utils.register_class(AdvancedGLBPreferences)
    
    # Add save handler
    if on_save_handler not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(on_save_handler)

def unregister():
    bpy.utils.unregister_class(ADVANCED_GLB_OT_export)
    bpy.utils.unregister_class(ADVANCED_GLB_PT_panel)
    bpy.utils.unregister_class(AdvancedGLBPreferences)
    
    # Remove save handler
    if on_save_handler in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(on_save_handler)

if __name__ == "__main__":

    register()

