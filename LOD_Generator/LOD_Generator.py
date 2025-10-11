bl_info = {
    "name": "LOD Generator",
    "author": "Giorgi Samukashvili (3DBullet)",
    "version": (1, 2),
    "blender": (4, 3, 0),
    "location": "View3D > Sidebar > Export",
    "description": "LOD Generation tool with texture resizing capabilities.\n\n" 
                   "Instructions:\n"
                   "1. Select the desired model\n"
                   "2. Ensure textures are saved externally (not packed)\n"
                   "3. Open side panel (N key) > Export tab\n"
                   "4. Set LOD count and reduction percentages\n"
                   "5. Click 'Generate LODs'\n\n"
                   "Note: Creates LOD folders with resized textures\n"
                   "Supports PNG/JPG formats | Minimum texture size: 512px",
    "warning": "",
    "category": "Object",
}

import bpy
import os
import re
from bpy.types import Operator, Panel
from bpy.props import IntProperty, FloatProperty, BoolProperty, EnumProperty

class LODGeneratorProperties(bpy.types.PropertyGroup):
    num_lods: IntProperty(
        name="Number of LODs",
        default=3,
        min=1,
        max=10
    )
    face_reduction: FloatProperty(
        name="Reduction per LOD (%)",
        default=50.0,
        min=1.0,
        max=99.0,
        subtype='PERCENTAGE'
    )
    process_textures: BoolProperty(
        name="Resize Textures",
        default=True
    )
    include_sep: BoolProperty(
        name="Include -sep",
        default=True,
        description="Add -sep suffix to LOD object names"
    )

class LODGeneratorPanel(Panel):
    bl_label = "LOD Generator"
    bl_idname = "OBJECT_PT_lod_generator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Export"

    def draw(self, context):
        layout = self.layout
        props = context.scene.lod_props
        layout.prop(props, "num_lods")
        layout.prop(props, "face_reduction")
        layout.prop(props, "process_textures")
        layout.prop(props, "include_sep")
        
        # Two buttons: Selective and Full generation
        row = layout.row()
        row.operator("object.generate_lods_selected", icon='OBJECT_DATA')
        row.operator("object.generate_lods_all", icon='SCENE_DATA')
        
        layout.label(text="Selective: Selected objects", icon='DOT')
        layout.label(text="Full: All mesh objects", icon='DOT')

class OBJECT_OT_GenerateLODsSelected(Operator):
    bl_label = "Generate LODs Selected"
    bl_idname = "object.generate_lods_selected"
    bl_description = "Generate LODs for selected objects only"
    bl_options = {'REGISTER', 'UNDO'}

    texture_action: EnumProperty(
        items=[('REPLACE', "Replace", "Overwrite existing textures"),
               ('SKIP', "Skip", "Keep existing textures")],
        default='REPLACE'
    )

    def invoke(self, context, event):
        # Check if any objects are selected
        if not context.selected_objects:
            self.report({'ERROR'}, "No objects selected")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        if not hasattr(self, 'existing_files'):
            layout.label(text="This operation may freeze Blender!", icon='ERROR')
            layout.label(text="Recommended:", icon='BLANK1')
            layout.label(text="1. Save your work first")
            layout.label(text="2. Close other applications")
            layout.label(text="3. Be patient during processing")
        else:
            layout.label(text="Existing textures found:", icon='ERROR')
            col = layout.column(align=True)
            col.scale_y = 0.7
            for f in self.existing_files[:3]:
                col.label(text=os.path.basename(f))
            if len(self.existing_files) > 3:
                col.label(text=f"...and {len(self.existing_files)-3} more")
            layout.separator()
            layout.prop(self, "texture_action", expand=True)

    def check_existing_files(self, context):
        props = context.scene.lod_props
        blend_path = bpy.path.abspath("//")
        existing_files = []

        for lod in range(1, props.num_lods + 1):
            lod_folder = os.path.join(blend_path, f"LOD{lod}")
            if os.path.exists(lod_folder):
                for file in os.listdir(lod_folder):
                    if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                        existing_files.append(os.path.join(lod_folder, file))
        return existing_files

    def execute(self, context):
        if not hasattr(self, 'existing_files'):
            self.existing_files = self.check_existing_files(context)
            if self.existing_files and context.scene.lod_props.process_textures:
                return context.window_manager.invoke_props_dialog(self, width=400)
            else:
                return self._process_lods(context, context.selected_objects)
        else:
            return self._process_lods(context, context.selected_objects)

    def _cleanup_existing_lods(self, original_obj):
        """Remove existing LOD objects and collections to prevent duplicates"""
        props = bpy.context.scene.lod_props
        
        # Pattern to match LOD objects for this original object
        base_name = self._get_base_name(original_obj.name)
        lod_pattern = re.compile(rf"^{re.escape(base_name)}(?:\s?-\s?sep)?_LOD\d+$")
        
        # Remove existing LOD objects
        objects_to_remove = []
        for obj in bpy.data.objects:
            if lod_pattern.match(obj.name) and obj != original_obj:
                objects_to_remove.append(obj)
        
        for obj in objects_to_remove:
            bpy.data.objects.remove(obj, do_unlink=True)
        
        # Remove existing LOD collections
        collections_to_remove = []
        lod_collection_name = f"{original_obj.name}_LODs"
        if lod_collection_name in bpy.data.collections:
            lod_collection = bpy.data.collections[lod_collection_name]
            # Unlink all objects from the collection first
            for obj in list(lod_collection.objects):
                lod_collection.objects.unlink(obj)
            # Remove the collection
            collections_to_remove.append(lod_collection)
        
        for coll in collections_to_remove:
            bpy.data.collections.remove(coll)

    def _get_base_name(self, name):
        """Remove existing -sep variants from name"""
        # Remove -sep (with or without space)
        base_name = re.sub(r'\s?-\s?sep$', '', name)
        # Also remove any existing _LOD suffix
        base_name = re.sub(r'_LOD\d+$', '', base_name)
        return base_name

    def _get_parent_collection(self, original_obj):
        """Get a suitable parent collection that is not a LOD collection"""
        # Get all collections the original object is in
        original_collections = original_obj.users_collection
        
        if not original_collections:
            # If object is not in any collection, use scene collection
            return bpy.context.scene.collection
        
        # Prefer non-LOD collections
        non_lod_collections = [coll for coll in original_collections if not coll.name.endswith('_LODs')]
        
        if non_lod_collections:
            return non_lod_collections[0]
        else:
            # If all are LOD collections, use the first one (we'll create LOD collection as sibling)
            return original_collections[0]

    def _process_lods(self, context, objects):
        props = context.scene.lod_props
        
        if not objects:
            self.report({'ERROR'}, "No objects to process")
            return {'CANCELLED'}

        reduction = props.face_reduction / 100.0

        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        processed_count = 0
        for original_obj in objects:
            if original_obj.type != 'MESH':
                continue
                
            # Clean up existing LODs first to prevent duplicates
            self._cleanup_existing_lods(original_obj)

            # Create LOD collection
            lod_collection = self._create_lod_collection(original_obj)

            current_base = original_obj
            for lod in range(1, props.num_lods + 1):
                # Duplicate object
                bpy.ops.object.select_all(action='DESELECT')
                current_base.select_set(True)
                context.view_layer.objects.active = current_base
                
                # Store the original object name for verification
                original_name = current_base.name
                
                # Duplicate and verify
                bpy.ops.object.duplicate()
                lod_obj = context.active_object
                
                # FIX: Check if duplication was successful
                if lod_obj is None:
                    self.report({'WARNING'}, f"Failed to duplicate object for LOD{lod}. Skipping.")
                    continue
                
                # Additional safety check - make sure we didn't get the original object
                if lod_obj == current_base:
                    self.report({'WARNING'}, f"Duplication failed - got original object for LOD{lod}. Skipping.")
                    continue

                # Generate LOD name
                base_name = self._get_base_name(original_obj.name)
                if props.include_sep:
                    lod_obj.name = f"{base_name}-sep_LOD{lod}"
                else:
                    lod_obj.name = f"{base_name}_LOD{lod}"

                # Move to LOD collection
                if lod_obj.name not in lod_collection.objects:
                    # Remove from all current collections
                    for coll in lod_obj.users_collection:
                        coll.objects.unlink(lod_obj)
                    # Add to LOD collection
                    lod_collection.objects.link(lod_obj)

                # Apply decimate modifier
                mod = lod_obj.modifiers.new(name="Decimate", type='DECIMATE')
                mod.ratio = 1 - reduction
                try:
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                except Exception as e:
                    self.report({'WARNING'}, f"Modifier error on {lod_obj.name}: {str(e)}")
                    # Continue with next LOD instead of failing completely

                # Process textures
                if props.process_textures:
                    self._process_textures(lod_obj, lod, reduction)

                current_base = lod_obj

            processed_count += 1

        # Select original objects again
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            if obj.type == 'MESH':
                obj.select_set(True)
        if objects:
            context.view_layer.objects.active = objects[0]

        self.report({'INFO'}, f"LOD generation completed for {processed_count} objects!")
        return {'FINISHED'}

    def _create_lod_collection(self, original_obj):
        """Create LOD collection and hide it by default"""
        collection_name = f"{original_obj.name}_LODs"
        
        # Remove existing collection if it exists
        if collection_name in bpy.data.collections:
            old_coll = bpy.data.collections[collection_name]
            bpy.data.collections.remove(old_coll)
        
        # Create new collection
        lod_collection = bpy.data.collections.new(collection_name)
        
        # Find parent collection (not a LOD collection)
        parent_collection = self._get_parent_collection(original_obj)
        
        # Link the LOD collection to parent
        parent_collection.children.link(lod_collection)
        
        # Hide the collection
        lod_collection.hide_viewport = True
        lod_collection.hide_render = True
        
        return lod_collection

    def _process_textures(self, lod_obj, lod_level, reduction):
        blend_path = bpy.path.abspath("//")
        lod_folder = os.path.join(blend_path, f"LOD{lod_level}")
        os.makedirs(lod_folder, exist_ok=True)

        for mat_slot in lod_obj.material_slots:
            if not mat_slot.material or not mat_slot.material.use_nodes:
                continue

            # Duplicate material
            new_mat = mat_slot.material.copy()
            
            # Generate material name
            base_name = self._get_base_name(mat_slot.material.name)
            if bpy.context.scene.lod_props.include_sep:
                new_mat.name = f"{base_name}-sep_LOD{lod_level}"
            else:
                new_mat.name = f"{base_name}_LOD{lod_level}"
                
            mat_slot.material = new_mat

            # Process texture nodes
            for node in new_mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    self._resize_texture(node.image, lod_folder, lod_level, reduction)

    def _resize_texture(self, img, lod_folder, lod_level, reduction):
        try:
            # Get base name from image name
            base_name = self._get_base_name(img.name)
            
            # Sanitize filename
            valid_chars = "-_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            sanitized_name = ''.join(c for c in base_name if c in valid_chars)
            if not sanitized_name:
                sanitized_name = f"texture_{lod_level}"

            # Add -sep if enabled
            if bpy.context.scene.lod_props.include_sep:
                sanitized_name = f"{sanitized_name}-sep"

            # Handle different image sources
            if img.source == 'TILED':
                sanitized_name = f"uvtile_{sanitized_name}"
                ext = ".png"
            else:
                ext = os.path.splitext(img.filepath)[1].lower() if img.filepath else ".png"
                if ext not in ('.png', '.jpg', '.jpeg'):
                    ext = ".png"

            # Create target filename
            target_name = f"{sanitized_name}_LOD{lod_level}{ext}"
            target_path = os.path.join(lod_folder, target_name)

            # Skip existing files if requested
            if os.path.exists(target_path) and self.texture_action == 'SKIP':
                return

            # Calculate dimensions
            orig_width, orig_height = img.size
            new_width = max(512, int(orig_width * (1 - reduction)))
            new_height = max(512, int(orig_height * (1 - reduction)))

            # Maintain aspect ratio
            aspect = orig_width / orig_height
            if new_width / new_height > aspect:
                new_height = max(512, int(new_width / aspect))
            else:
                new_width = max(512, int(new_height * aspect))

            # Create new image
            new_img = bpy.data.images.new(
                name=f"{sanitized_name}_LOD{lod_level}",
                width=new_width,
                height=new_height
            )

            # Copy and scale pixel data
            img.scale(new_width, new_height)
            new_img.pixels = img.pixels[:]
            img.reload()

            # Save settings
            new_img.filepath_raw = target_path
            new_img.file_format = 'PNG' if ext == '.png' else 'JPEG'
            new_img.save()

            return new_img

        except Exception as e:
            print(f"Error processing texture {img.name}: {str(e)}")
            self.report({'WARNING'}, f"Skipped {img.name} (see console for details)")
            return None

class OBJECT_OT_GenerateLODsAll(Operator):
    bl_label = "Generate LODs All"
    bl_idname = "object.generate_lods_all"
    bl_description = "Generate LODs for all mesh objects in the scene"
    bl_options = {'REGISTER', 'UNDO'}

    texture_action: EnumProperty(
        items=[('REPLACE', "Replace", "Overwrite existing textures"),
               ('SKIP', "Skip", "Keep existing textures")],
        default='REPLACE'
    )

    def invoke(self, context, event):
        # Check if there are any mesh objects
        mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH']
        if not mesh_objects:
            self.report({'ERROR'}, "No mesh objects in scene")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        if not hasattr(self, 'existing_files'):
            layout.label(text="Generate LODs for ALL mesh objects?", icon='QUESTION')
            layout.label(text="This may take a long time!", icon='ERROR')
            layout.label(text="Recommended:", icon='BLANK1')
            layout.label(text="1. Save your work first")
            layout.label(text="2. Close other applications")
            layout.label(text="3. Be patient during processing")
        else:
            layout.label(text="Existing textures found:", icon='ERROR')
            col = layout.column(align=True)
            col.scale_y = 0.7
            for f in self.existing_files[:3]:
                col.label(text=os.path.basename(f))
            if len(self.existing_files) > 3:
                col.label(text=f"...and {len(self.existing_files)-3} more")
            layout.separator()
            layout.prop(self, "texture_action", expand=True)

    def check_existing_files(self, context):
        props = context.scene.lod_props
        blend_path = bpy.path.abspath("//")
        existing_files = []

        for lod in range(1, props.num_lods + 1):
            lod_folder = os.path.join(blend_path, f"LOD{lod}")
            if os.path.exists(lod_folder):
                for file in os.listdir(lod_folder):
                    if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                        existing_files.append(os.path.join(lod_folder, file))
        return existing_files

    def execute(self, context):
        if not hasattr(self, 'existing_files'):
            self.existing_files = self.check_existing_files(context)
            if self.existing_files and context.scene.lod_props.process_textures:
                return context.window_manager.invoke_props_dialog(self, width=400)
            else:
                return self._process_lods(context)
        else:
            return self._process_lods(context)

    def _process_lods(self, context):
        props = context.scene.lod_props
        
        # Get all mesh objects in the scene
        mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH']
        
        if not mesh_objects:
            self.report({'ERROR'}, "No mesh objects found")
            return {'CANCELLED'}

        reduction = props.face_reduction / 100.0

        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        processed_count = 0
        for original_obj in mesh_objects:
            # Use the same methods from the selected operator
            self._cleanup_existing_lods(original_obj)
            lod_collection = self._create_lod_collection(original_obj)

            current_base = original_obj
            for lod in range(1, props.num_lods + 1):
                bpy.ops.object.select_all(action='DESELECT')
                current_base.select_set(True)
                context.view_layer.objects.active = current_base
                
                # Store the original object name for verification
                original_name = current_base.name
                
                # Duplicate and verify
                bpy.ops.object.duplicate()
                lod_obj = context.active_object
                
                # FIX: Check if duplication was successful
                if lod_obj is None:
                    self.report({'WARNING'}, f"Failed to duplicate object for LOD{lod}. Skipping.")
                    continue
                
                # Additional safety check - make sure we didn't get the original object
                if lod_obj == current_base:
                    self.report({'WARNING'}, f"Duplication failed - got original object for LOD{lod}. Skipping.")
                    continue
                
                base_name = self._get_base_name(original_obj.name)
                if props.include_sep:
                    lod_obj.name = f"{base_name}-sep_LOD{lod}"
                else:
                    lod_obj.name = f"{base_name}_LOD{lod}"

                # Move to LOD collection
                if lod_obj.name not in lod_collection.objects:
                    for coll in lod_obj.users_collection:
                        coll.objects.unlink(lod_obj)
                    lod_collection.objects.link(lod_obj)

                # Apply decimate modifier
                mod = lod_obj.modifiers.new(name="Decimate", type='DECIMATE')
                mod.ratio = 1 - reduction
                try:
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                except Exception as e:
                    self.report({'WARNING'}, f"Modifier error on {lod_obj.name}: {str(e)}")
                    continue

                # Process textures
                if props.process_textures:
                    self._process_textures(lod_obj, lod, reduction)

                current_base = lod_obj

            processed_count += 1

        self.report({'INFO'}, f"LOD generation completed for {processed_count} objects!")
        return {'FINISHED'}

    # Reuse the same helper methods from OBJECT_OT_GenerateLODsSelected
    def _cleanup_existing_lods(self, original_obj):
        """Remove existing LOD objects and collections to prevent duplicates"""
        props = bpy.context.scene.lod_props
        
        # Pattern to match LOD objects for this original object
        base_name = self._get_base_name(original_obj.name)
        lod_pattern = re.compile(rf"^{re.escape(base_name)}(?:\s?-\s?sep)?_LOD\d+$")
        
        # Remove existing LOD objects
        objects_to_remove = []
        for obj in bpy.data.objects:
            if lod_pattern.match(obj.name) and obj != original_obj:
                objects_to_remove.append(obj)
        
        for obj in objects_to_remove:
            bpy.data.objects.remove(obj, do_unlink=True)
        
        # Remove existing LOD collections
        collections_to_remove = []
        lod_collection_name = f"{original_obj.name}_LODs"
        if lod_collection_name in bpy.data.collections:
            lod_collection = bpy.data.collections[lod_collection_name]
            for obj in list(lod_collection.objects):
                lod_collection.objects.unlink(obj)
            collections_to_remove.append(lod_collection)
        
        for coll in collections_to_remove:
            bpy.data.collections.remove(coll)

    def _get_base_name(self, name):
        """Remove existing -sep variants from name"""
        base_name = re.sub(r'\s?-\s?sep$', '', name)
        base_name = re.sub(r'_LOD\d+$', '', base_name)
        return base_name

    def _get_parent_collection(self, original_obj):
        """Get a suitable parent collection that is not a LOD collection"""
        original_collections = original_obj.users_collection
        
        if not original_collections:
            return bpy.context.scene.collection
        
        non_lod_collections = [coll for coll in original_collections if not coll.name.endswith('_LODs')]
        
        if non_lod_collections:
            return non_lod_collections[0]
        else:
            return original_collections[0]

    def _create_lod_collection(self, original_obj):
        """Create LOD collection and hide it by default"""
        collection_name = f"{original_obj.name}_LODs"
        
        if collection_name in bpy.data.collections:
            old_coll = bpy.data.collections[collection_name]
            bpy.data.collections.remove(old_coll)
        
        lod_collection = bpy.data.collections.new(collection_name)
        parent_collection = self._get_parent_collection(original_obj)
        parent_collection.children.link(lod_collection)
        
        lod_collection.hide_viewport = True
        lod_collection.hide_render = True
        
        return lod_collection

    def _process_textures(self, lod_obj, lod_level, reduction):
        blend_path = bpy.path.abspath("//")
        lod_folder = os.path.join(blend_path, f"LOD{lod_level}")
        os.makedirs(lod_folder, exist_ok=True)

        for mat_slot in lod_obj.material_slots:
            if not mat_slot.material or not mat_slot.material.use_nodes:
                continue

            new_mat = mat_slot.material.copy()
            base_name = self._get_base_name(mat_slot.material.name)
            if bpy.context.scene.lod_props.include_sep:
                new_mat.name = f"{base_name}-sep_LOD{lod_level}"
            else:
                new_mat.name = f"{base_name}_LOD{lod_level}"
            mat_slot.material = new_mat

            for node in new_mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    self._resize_texture(node.image, lod_folder, lod_level, reduction)

    def _resize_texture(self, img, lod_folder, lod_level, reduction):
        try:
            base_name = self._get_base_name(img.name)
            valid_chars = "-_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
            sanitized_name = ''.join(c for c in base_name if c in valid_chars)
            if not sanitized_name:
                sanitized_name = f"texture_{lod_level}"

            if bpy.context.scene.lod_props.include_sep:
                sanitized_name = f"{sanitized_name}-sep"

            if img.source == 'TILED':
                sanitized_name = f"uvtile_{sanitized_name}"
                ext = ".png"
            else:
                ext = os.path.splitext(img.filepath)[1].lower() if img.filepath else ".png"
                if ext not in ('.png', '.jpg', '.jpeg'):
                    ext = ".png"

            target_name = f"{sanitized_name}_LOD{lod_level}{ext}"
            target_path = os.path.join(lod_folder, target_name)

            if os.path.exists(target_path) and self.texture_action == 'SKIP':
                return

            orig_width, orig_height = img.size
            new_width = max(512, int(orig_width * (1 - reduction)))
            new_height = max(512, int(orig_height * (1 - reduction)))

            aspect = orig_width / orig_height
            if new_width / new_height > aspect:
                new_height = max(512, int(new_width / aspect))
            else:
                new_width = max(512, int(new_height * aspect))

            new_img = bpy.data.images.new(
                name=f"{sanitized_name}_LOD{lod_level}",
                width=new_width,
                height=new_height
            )

            img.scale(new_width, new_height)
            new_img.pixels = img.pixels[:]
            img.reload()

            new_img.filepath_raw = target_path
            new_img.file_format = 'PNG' if ext == '.png' else 'JPEG'
            new_img.save()

            return new_img

        except Exception as e:
            print(f"Error processing texture {img.name}: {str(e)}")
            self.report({'WARNING'}, f"Skipped {img.name} (see console for details)")
            return None

classes = (LODGeneratorProperties, LODGeneratorPanel, OBJECT_OT_GenerateLODsSelected, OBJECT_OT_GenerateLODsAll)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.lod_props = bpy.props.PointerProperty(type=LODGeneratorProperties)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.lod_props

if __name__ == "__main__":
    register()
