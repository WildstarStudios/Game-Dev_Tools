bl_info = {
    "name": "Advanced GLB Auto-Exporter",
    "author": "Your Name",
    "version": (1, 1),
    "blender": (4, 3, 0),
    "location": "View3D > Sidebar > GLB Export",
    "description": "Advanced GLB export with hierarchical collection separation",
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
            scene = context.scene
            export_path = get_export_path(scene)
            if export_path:
                if scene.glb_export_scope == 'SCENE':
                    self.report({'INFO'}, f"Exported scene to {export_path}")
                else:
                    self.report({'INFO'}, f"Exported {scene.glb_export_scope.lower()} to {export_path}")
            else:
                self.report({'WARNING'}, "Export completed but no path was set")
        return result

class ADVANCED_GLB_PT_panel(bpy.types.Panel):
    bl_label = "GLB Auto-Export"
    bl_idname = "VIEW3D_PT_advanced_glb_export"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'GLB Export'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Export path with per-file storage
        box = layout.box()
        box.label(text="Export Path (Per File):")
        box.prop(scene, "glb_export_path", text="")
        
        # Show current effective path
        export_path = get_export_path(scene)
        if export_path:
            box.label(text=f"Will export to: {export_path}", icon='FILE_TICK')
        else:
            box.label(text="No export path set!", icon='ERROR')
            box.label(text="Set a path to enable export")
        
        # Use global default option
        box.prop(scene, "glb_use_global_default", text="Use Global Default Path")
        if scene.glb_use_global_default:
            box.label(text=f"Global default: {context.preferences.addons[__name__].preferences.global_export_path}")
        
        # Auto-export toggle
        layout.prop(scene, "glb_auto_export_on_save", text="Enable Auto-Export on Save")
        
        # Export settings box
        settings_box = layout.box()
        settings_box.label(text="Export Settings:")
        settings_box.prop(scene, "glb_export_individual_origins")
        settings_box.prop(scene, "glb_apply_modifiers")
        
        # Export scope selection
        settings_box.prop(scene, "glb_export_scope", text="Export Scope")
        
        # Detailed listing options
        list_box = layout.box()
        list_box.prop(scene, "glb_show_detailed_list", text="Show Detailed List")
        
        if scene.glb_show_detailed_list:
            list_box.prop(scene, "glb_show_hidden_objects", text="Show Hidden Objects")
        
        # Summary of what will be exported
        summary_box = layout.box()
        summary_box.label(text="Export Summary:")
        
        # Get and display detailed summary
        summary_lines = get_export_summary(scene)
        for line in summary_lines:
            summary_box.label(text=line)
        
        # Export button (disabled if no path)
        if export_path:
            layout.operator("export.advanced_glb", icon='EXPORT')
        else:
            col = layout.column()
            col.enabled = False
            col.operator("export.advanced_glb", icon='EXPORT')
            layout.label(text="Set export path first!", icon='INFO')

class AdvancedGLBPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    global_export_path: StringProperty(
        name="Global Default Export Path",
        subtype='FILE_PATH',
        default="",
        description="Global default path for GLB exports (used when per-file path is not set)"
    )

# Scene properties (stored per .blend file)
def init_scene_properties():
    """Initialize properties for each scene"""
    bpy.types.Scene.glb_export_path = StringProperty(
        name="Export Path",
        subtype='FILE_PATH',
        default="",
        description="Path for GLB exports (saved with this .blend file)"
    )
    
    bpy.types.Scene.glb_use_global_default = BoolProperty(
        name="Use Global Default",
        default=False,
        description="Use the global default path instead of per-file path"
    )
    
    bpy.types.Scene.glb_auto_export_on_save = BoolProperty(
        name="Auto Export on Save",
        default=False,
        description="Automatically export GLB when saving this Blender file"
    )
    
    bpy.types.Scene.glb_export_individual_origins = BoolProperty(
        name="Export by Individual Origins",
        default=False,
        description="Export each object with its own origin point at (0,0,0)"
    )
    
    bpy.types.Scene.glb_apply_modifiers = BoolProperty(
        name="Apply Modifiers",
        default=True,
        description="Apply modifiers before export"
    )
    
    bpy.types.Scene.glb_export_scope = EnumProperty(
        name="Export Scope",
        items=[
            ('SCENE', "Scene", "Export entire scene"),
            ('COLLECTION', "Collection", "Export collections individually"),
            ('OBJECT', "Object", "Export objects individually"),
        ],
        default='SCENE',
        description="Select what to export"
    )
    
    bpy.types.Scene.glb_show_detailed_list = BoolProperty(
        name="Show Detailed List",
        default=False,
        description="Display detailed list of objects/collections to be exported"
    )
    
    bpy.types.Scene.glb_show_hidden_objects = BoolProperty(
        name="Show Hidden Objects",
        default=False,
        description="Include hidden objects in the detailed list"
    )

def get_export_path(scene):
    """Get the effective export path (per-file or global default)"""
    if scene.glb_use_global_default:
        # Use global default from preferences
        addon_prefs = bpy.context.preferences.addons[__name__].preferences
        return addon_prefs.global_export_path
    else:
        # Use per-file path
        return scene.glb_export_path

def get_export_summary(scene):
    """Generate detailed summary of what will be exported"""
    summary_lines = []
    
    if scene.glb_export_scope == 'SCENE':
        objects_to_export = [obj for obj in bpy.data.objects if should_export_object(obj)]
        if not scene.glb_show_detailed_list:
            summary_lines.append(f"Scene: {len(objects_to_export)} objects")
        else:
            summary_lines.append("Scene Objects to Export:")
            for obj in objects_to_export:
                summary_lines.append(f"  - {obj.name} ({obj.type})")
            
            if scene.glb_show_hidden_objects:
                hidden_objects = [obj for obj in bpy.data.objects if not should_export_object(obj)]
                if hidden_objects:
                    summary_lines.append("\nHidden Objects (Not Exported):")
                    for obj in hidden_objects:
                        collection_names = ", ".join([col.name for col in get_object_collections(obj)])
                        summary_lines.append(f"  - {obj.name} ({obj.type}) in {collection_names}")
    
    elif scene.glb_export_scope == 'COLLECTION':
        # Get all export roots (collections that should be exported separately)
        export_roots = find_collection_export_roots(bpy.context.scene.collection)
        
        if not scene.glb_show_detailed_list:
            summary_lines.append(f"{len(export_roots)} export roots")
        else:
            summary_lines.append("Collection Export Roots:")
            for root_collection, collections_in_root in export_roots.items():
                # Count objects in this export root
                all_objects = []
                for col in collections_in_root:
                    all_objects.extend([obj for obj in col.all_objects if should_export_object(obj)])
                
                summary_lines.append(f"\n'{root_collection.name}' (Export Root):")
                summary_lines.append(f"  - Contains {len(collections_in_root)} collections")
                summary_lines.append(f"  - {len(all_objects)} exportable objects")
                
                if scene.glb_show_detailed_list:
                    for col in collections_in_root:
                        exportable_objs = [obj for obj in col.all_objects if should_export_object(obj)]
                        status = " (Hidden)" if col.hide_viewport or col.hide_render else ""
                        summary_lines.append(f"    - Collection '{col.name}'{status}: {len(exportable_objs)} objects")
    
    elif scene.glb_export_scope == 'OBJECT':
        objects_to_export = [obj for obj in bpy.data.objects if should_export_object(obj)]
        if not scene.glb_show_detailed_list:
            summary_lines.append(f"{len(objects_to_export)} objects")
        else:
            summary_lines.append("Objects to Export:")
            for obj in objects_to_export:
                collection_names = ", ".join([col.name for col in get_object_collections(obj)])
                summary_lines.append(f"  - {obj.name} ({obj.type}) in {collection_names}")
            
            if scene.glb_show_hidden_objects:
                hidden_objects = [obj for obj in bpy.data.objects if not should_export_object(obj)]
                if hidden_objects:
                    summary_lines.append("\nHidden Objects (Not Exported):")
                    for obj in hidden_objects:
                        collection_names = ", ".join([col.name for col in get_object_collections(obj)])
                        reason = get_exclusion_reason(obj)
                        summary_lines.append(f"  - {obj.name} ({obj.type}) in {collection_names} - {reason}")
    
    # Add counts if detailed list is empty
    if not summary_lines:
        if scene.glb_export_scope == 'SCENE':
            obj_count = sum(1 for obj in bpy.data.objects if should_export_object(obj))
            summary_lines.append(f"Scene: {obj_count} objects")
        elif scene.glb_export_scope == 'COLLECTION':
            export_roots = find_collection_export_roots(bpy.context.scene.collection)
            summary_lines.append(f"{len(export_roots)} export roots")
        elif scene.glb_export_scope == 'OBJECT':
            obj_count = sum(1 for obj in bpy.data.objects if should_export_object(obj))
            summary_lines.append(f"{obj_count} objects")
    
    return summary_lines

def find_collection_export_roots(scene_collection):
    """Find all collection export roots based on -sep suffix"""
    export_roots = {}
    
    def traverse_collections(collection, current_root=None):
        """Recursively traverse collections to find export roots"""
        # Skip collections that shouldn't be exported
        if not should_export_collection(collection):
            return
        
        # Check if this collection is a new export root (-sep collection)
        if is_separate_export_collection(collection):
            # This becomes a new export root
            current_root = collection
            if collection not in export_roots:
                export_roots[collection] = []
        
        # If we're in an export root, add this collection to it
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
    scene = context.scene
    export_path = get_export_path(scene)
    
    if not export_path:
        print("Export failed: No export path specified for this file")
        return {'CANCELLED'}
    
    # Ensure directory exists
    dirname = os.path.dirname(export_path)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname)
    
    # Ensure .glb extension
    if not export_path.lower().endswith('.glb'):
        export_path += '.glb'
    
    # Store original transforms for restoration
    original_transforms = {}
    objects_to_export = []
    
    try:
        # Handle individual origins if requested
        if scene.glb_export_individual_origins:
            # Collect objects to export
            if scene.glb_export_scope == 'SCENE':
                objects_to_export = [obj for obj in bpy.data.objects 
                                    if should_export_object(obj)]
            elif scene.glb_export_scope == 'COLLECTION':
                # For collection export, we'll handle this per export root
                export_roots = find_collection_export_roots(bpy.context.scene.collection)
                for root_collection, collections_in_root in export_roots.items():
                    for col in collections_in_root:
                        objects_to_export.extend([obj for obj in col.all_objects 
                                                if should_export_object(obj)])
            elif scene.glb_export_scope == 'OBJECT':
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
            'filepath': export_path,
            'export_format': 'GLB',
            'export_apply': scene.glb_apply_modifiers,
            'export_yup': True
        }
        
        # Handle export scope
        if scene.glb_export_scope == 'SCENE':
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
                print(f"Exported scene to: {export_path}")
                return {'FINISHED'}
            except Exception as e:
                print(f"Scene export failed: {str(e)}")
                return {'CANCELLED'}
        
        elif scene.glb_export_scope == 'COLLECTION':
            # Export each collection export root individually
            export_roots = find_collection_export_roots(bpy.context.scene.collection)
            success_count = 0
            
            for root_collection, collections_in_root in export_roots.items():
                # Create path for this export root
                root_path = os.path.join(
                    os.path.dirname(export_path),
                    f"{os.path.splitext(os.path.basename(export_path))[0]}_{root_collection.name}.glb"
                )
                
                # Select all objects from all collections in this export root
                bpy.ops.object.select_all(action='DESELECT')
                object_count = 0
                
                for col in collections_in_root:
                    for obj in col.all_objects:
                        if should_export_object(obj):
                            obj.select_set(True)
                            object_count += 1
                
                if object_count == 0:
                    print(f"Skipping export root '{root_collection.name}': No exportable objects")
                    continue
                
                # Update export settings for this export root
                root_settings = export_settings.copy()
                root_settings['filepath'] = root_path
                root_settings['use_selection'] = True
                
                try:
                    bpy.ops.export_scene.gltf(**root_settings)
                    print(f"Exported collection root '{root_collection.name}' to: {root_path}")
                    print(f"  - Contains {len(collections_in_root)} collections")
                    print(f"  - Exported {object_count} objects")
                    success_count += 1
                except Exception as e:
                    print(f"Collection export failed for '{root_collection.name}': {str(e)}")
            
            return {'FINISHED'} if success_count > 0 else {'CANCELLED'}
        
        elif scene.glb_export_scope == 'OBJECT':
            # Export each object individually
            success_count = 0
            for obj in bpy.data.objects:
                if not should_export_object(obj):
                    continue
                    
                # Create path for this object
                object_path = os.path.join(
                    os.path.dirname(export_path),
                    f"{os.path.splitext(os.path.basename(export_path))[0]}_{obj.name}.glb"
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
        if scene.glb_export_individual_origins and original_transforms:
            reset_origins(original_transforms)

@persistent
def on_save_handler(dummy):
    if not bpy.context.preferences.addons.get(__name__):
        return
    
    scene = bpy.context.scene
    
    # Check if auto-export is enabled for this scene
    if not scene.glb_auto_export_on_save:
        return
    
    # Skip unsaved files
    if not bpy.data.filepath:
        print("Auto-export skipped: Save your file first")
        return
    
    # Check if we have an export path
    export_path = get_export_path(scene)
    if not export_path:
        print("Auto-export skipped: No export path set for this file")
        return
    
    export_glb(bpy.context)

def register():
    # Initialize scene properties first
    init_scene_properties()
    
    # Register classes
    bpy.utils.register_class(ADVANCED_GLB_OT_export)
    bpy.utils.register_class(ADVANCED_GLB_PT_panel)
    bpy.utils.register_class(AdvancedGLBPreferences)
    
    # Add save handler
    if on_save_handler not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(on_save_handler)

def unregister():
    # Remove save handler
    if on_save_handler in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(on_save_handler)
    
    # Unregister classes
    bpy.utils.unregister_class(ADVANCED_GLB_OT_export)
    bpy.utils.unregister_class(ADVANCED_GLB_PT_panel)
    bpy.utils.unregister_class(AdvancedGLBPreferences)
    
    # Clean up scene properties
    del bpy.types.Scene.glb_export_path
    del bpy.types.Scene.glb_use_global_default
    del bpy.types.Scene.glb_auto_export_on_save
    del bpy.types.Scene.glb_export_individual_origins
    del bpy.types.Scene.glb_apply_modifiers
    del bpy.types.Scene.glb_export_scope
    del bpy.types.Scene.glb_show_detailed_list
    del bpy.types.Scene.glb_show_hidden_objects

if __name__ == "__main__":
    register()
