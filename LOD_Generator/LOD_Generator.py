bl_info = {
    "name": "LOD Generator rewritten",
    "author": "Wildstar Studios",
    "version": (1, 0),
    "blender": (4, 5, 0),
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
        description="Number of LOD levels to generate",
        default=3,
        min=1,
        max=10
    )
    face_reduction: FloatProperty(
        name="Reduction per LOD (%)",
        description="Percentage of faces to reduce for each LOD level",
        default=50.0,
        min=1.0,
        max=99.0,
        subtype='PERCENTAGE'
    )
    process_textures: BoolProperty(
        name="Resize Textures",
        description="Resize textures for each LOD level",
        default=True
    )
    include_sep: BoolProperty(
        name="Include -sep",
        description="Add -sep suffix to LOD names",
        default=True
    )
    sep_mode: EnumProperty(
        name="-sep Mode",
        description="Where to apply the -sep suffix",
        items=[
            ('COLLECTION', "Collection", "Apply -sep to collections only"),
            ('OBJECT', "Object", "Apply -sep to objects only"),
            ('BOTH', "Both", "Apply -sep to both collections and objects")
        ],
        default='COLLECTION'
    )
    hide_root_collection: BoolProperty(
        name="Hide Root Collection (-sk)",
        description="Hide the root LOD collection with -sk suffix",
        default=True
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
        
        # Settings
        layout.prop(props, "num_lods")
        layout.prop(props, "face_reduction")
        layout.prop(props, "process_textures")
        layout.prop(props, "include_sep")
        
        # Show sep mode only when include_sep is enabled
        if props.include_sep:
            layout.prop(props, "sep_mode")
        
        # Hide root collection toggle
        layout.prop(props, "hide_root_collection")
        
        # Buttons - Selective on the right as requested
        row = layout.row()
        row.operator("object.generate_lods_all", icon='SCENE_DATA', text="Full Generate")
        row.operator("object.generate_lods_selected", icon='OBJECT_DATA', text="Selective Generate")
        
        # Labels
        layout.label(text="Full: All mesh objects", icon='DOT')
        layout.label(text="Selective: Selected objects only", icon='DOT')

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
        # Check if the original object still exists
        if not original_obj or original_obj.name not in bpy.data.objects:
            return
            
        props = bpy.context.scene.lod_props
        
        # Pattern to match LOD objects for this original object
        base_name = self._get_base_name(original_obj.name)
        lod_pattern = re.compile(rf"^{re.escape(base_name)}(?:\s?-\s?sep)?_LOD\d+$")
        
        # Remove existing LOD objects
        objects_to_remove = []
        for obj in bpy.data.objects:
            # Check if object still exists before accessing its name
            if obj.name not in bpy.data.objects:
                continue
            if lod_pattern.match(obj.name) and obj != original_obj:
                objects_to_remove.append(obj)
        
        for obj in objects_to_remove:
            # Double-check object still exists before removing
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)

    def _get_base_name(self, name):
        """Remove existing -sep variants from name"""
        # Remove -sep (with or without space)
        base_name = re.sub(r'\s?-\s?sep$', '', name)
        # Also remove any existing _LOD suffix
        base_name = re.sub(r'_LOD\d+$', '', base_name)
        return base_name

    def _process_lods(self, context, objects):
        props = context.scene.lod_props
        
        if not objects:
            self.report({'ERROR'}, "No objects to process")
            return {'CANCELLED'}

        reduction = props.face_reduction / 100.0

        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Get or create the main LODs-sk collection
        main_lod_collection = self._get_or_create_main_lod_collection()

        processed_count = 0
        for original_obj in objects:
            # Skip if object no longer exists
            if original_obj.name not in bpy.data.objects:
                continue
                
            if original_obj.type != 'MESH':
                continue
                
            # Clean up existing LODs first to prevent duplicates
            self._cleanup_existing_lods(original_obj)

            # Create object's LOD collection inside main collection
            obj_lod_collection = self._create_object_lod_collection(original_obj, main_lod_collection)
            if obj_lod_collection is None:
                continue

            current_base = original_obj
            successful_lods = 0
            
            for lod in range(1, props.num_lods + 1):
                # Duplicate object
                bpy.ops.object.select_all(action='DESELECT')
                current_base.select_set(True)
                context.view_layer.objects.active = current_base
                
                # Store the original object name for verification
                original_name = current_base.name
                
                # Duplicate and verify
                try:
                    bpy.ops.object.duplicate()
                    lod_obj = context.active_object
                    
                    # Check if duplication was successful
                    if lod_obj is None or lod_obj == current_base:
                        self.report({'WARNING'}, f"Failed to duplicate object for LOD{lod}. Skipping.")
                        break  # Break out of the LOD loop for this object
                    
                    # Generate LOD name based on sep mode
                    base_name = self._get_base_name(original_obj.name)
                    
                    # Object naming logic
                    if props.include_sep and props.sep_mode in ['OBJECT', 'BOTH']:
                        lod_obj.name = f"{base_name}-sep_LOD{lod}"
                    else:
                        lod_obj.name = f"{base_name}_LOD{lod}"

                    # Create LOD level collection with -sep suffix inside object's collection
                    lod_level_collection = self._create_lod_level_collection(original_obj, lod, obj_lod_collection)
                    
                    # Move to LOD level collection
                    if lod_obj.name not in lod_level_collection.objects:
                        # Remove from all current collections
                        for coll in lod_obj.users_collection:
                            coll.objects.unlink(lod_obj)
                        # Add to LOD level collection
                        lod_level_collection.objects.link(lod_obj)

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
                    successful_lods += 1
                    
                except Exception as e:
                    self.report({'WARNING'}, f"Error creating LOD{lod}: {str(e)}")
                    break  # Break out of the LOD loop for this object

            processed_count += 1

        # Select original objects again
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            if obj.name in bpy.data.objects and obj.type == 'MESH':
                obj.select_set(True)
        if objects and objects[0].name in bpy.data.objects:
            context.view_layer.objects.active = objects[0]

        self.report({'INFO'}, f"LOD generation completed for {processed_count} objects!")
        return {'FINISHED'}

    def _get_or_create_main_lod_collection(self):
        """Get or create the main LODs-sk collection"""
        main_collection_name = "LODs-sk"
        
        # Remove existing main collection if it exists
        if main_collection_name in bpy.data.collections:
            old_coll = bpy.data.collections[main_collection_name]
            bpy.data.collections.remove(old_coll)
        
        # Create new main collection
        main_collection = bpy.data.collections.new(main_collection_name)
        
        # Link to scene collection
        bpy.context.scene.collection.children.link(main_collection)
        
        # Hide the main collection only if hide_root_collection is enabled
        if bpy.context.scene.lod_props.hide_root_collection:
            main_collection.hide_viewport = True
            main_collection.hide_render = True
        
        return main_collection

    def _create_object_lod_collection(self, original_obj, main_collection):
        """Create object's LOD collection inside main collection (no -sep suffix)"""
        # Check if object still exists
        if original_obj.name not in bpy.data.objects:
            return None
            
        base_name = self._get_base_name(original_obj.name)
        
        # Object collection name (no suffix)
        collection_name = f"{base_name}_LODs"
        
        # Remove existing collection if it exists in main
        if collection_name in main_collection.children:
            old_coll = main_collection.children[collection_name]
            # Remove all child collections first
            for child_coll in list(old_coll.children):
                bpy.data.collections.remove(child_coll)
            bpy.data.collections.remove(old_coll)
        
        # Create new object collection
        obj_collection = bpy.data.collections.new(collection_name)
        
        # Link to main collection
        main_collection.children.link(obj_collection)
        
        return obj_collection

    def _create_lod_level_collection(self, original_obj, lod_level, obj_collection):
        """Create LOD level collection with -sep suffix inside object's collection"""
        base_name = self._get_base_name(original_obj.name)
        
        # LOD level collection name with -sep
        collection_name = f"{base_name}_LOD{lod_level}-sep"
        
        # Remove existing collection if it exists in object collection
        if collection_name in obj_collection.children:
            old_coll = obj_collection.children[collection_name]
            bpy.data.collections.remove(old_coll)
        
        # Create new LOD level collection
        lod_collection = bpy.data.collections.new(collection_name)
        
        # Link to object collection
        obj_collection.children.link(lod_collection)
        
        return lod_collection

    def _process_textures(self, lod_obj, lod_level, reduction):
        # Check if object still exists
        if lod_obj.name not in bpy.data.objects:
            return
            
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

        # Get or create the main LODs-sk collection
        main_lod_collection = self._get_or_create_main_lod_collection()

        processed_count = 0
        for original_obj in mesh_objects:
            # Check if object still exists
            if original_obj.name not in bpy.data.objects:
                continue
                
            # Use the same methods from the selected operator
            self._cleanup_existing_lods(original_obj)
            obj_lod_collection = self._create_object_lod_collection(original_obj, main_lod_collection)
            
            if obj_lod_collection is None:
                continue

            current_base = original_obj
            successful_lods = 0
            
            for lod in range(1, props.num_lods + 1):
                bpy.ops.object.select_all(action='DESELECT')
                current_base.select_set(True)
                context.view_layer.objects.active = current_base
                
                # Store the original object name for verification
                original_name = current_base.name
                
                try:
                    # Duplicate and verify
                    bpy.ops.object.duplicate()
                    lod_obj = context.active_object
                    
                    # Check if duplication was successful
                    if lod_obj is None or lod_obj == current_base:
                        self.report({'WARNING'}, f"Failed to duplicate object for LOD{lod}. Skipping.")
                        break  # Break out of the LOD loop for this object
                    
                    base_name = self._get_base_name(original_obj.name)
                    
                    # Object naming logic
                    if props.include_sep and props.sep_mode in ['OBJECT', 'BOTH']:
                        lod_obj.name = f"{base_name}-sep_LOD{lod}"
                    else:
                        lod_obj.name = f"{base_name}_LOD{lod}"

                    # Create LOD level collection with -sep suffix inside object's collection
                    lod_level_collection = self._create_lod_level_collection(original_obj, lod, obj_lod_collection)
                    
                    # Move to LOD level collection
                    if lod_obj.name not in lod_level_collection.objects:
                        for coll in lod_obj.users_collection:
                            coll.objects.unlink(lod_obj)
                        lod_level_collection.objects.link(lod_obj)

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
                    successful_lods += 1
                    
                except Exception as e:
                    self.report({'WARNING'}, f"Error creating LOD{lod}: {str(e)}")
                    break  # Break out of the LOD loop for this object

            processed_count += 1

        self.report({'INFO'}, f"LOD generation completed for {processed_count} objects!")
        return {'FINISHED'}

    # Reuse the same helper methods from OBJECT_OT_GenerateLODsSelected
    def _cleanup_existing_lods(self, original_obj):
        """Remove existing LOD objects and collections to prevent duplicates"""
        # Check if the original object still exists
        if not original_obj or original_obj.name not in bpy.data.objects:
            return
            
        props = bpy.context.scene.lod_props
        
        # Pattern to match LOD objects for this original object
        base_name = self._get_base_name(original_obj.name)
        lod_pattern = re.compile(rf"^{re.escape(base_name)}(?:\s?-\s?sep)?_LOD\d+$")
        
        # Remove existing LOD objects
        objects_to_remove = []
        for obj in bpy.data.objects:
            # Check if object still exists before accessing its name
            if obj.name not in bpy.data.objects:
                continue
            if lod_pattern.match(obj.name) and obj != original_obj:
                objects_to_remove.append(obj)
        
        for obj in objects_to_remove:
            # Double-check object still exists before removing
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)

    def _get_base_name(self, name):
        """Remove existing -sep variants from name"""
        base_name = re.sub(r'\s?-\s?sep$', '', name)
        base_name = re.sub(r'_LOD\d+$', '', base_name)
        return base_name

    def _get_or_create_main_lod_collection(self):
        """Get or create the main LODs-sk collection"""
        main_collection_name = "LODs-sk"
        
        # Remove existing main collection if it exists
        if main_collection_name in bpy.data.collections:
            old_coll = bpy.data.collections[main_collection_name]
            bpy.data.collections.remove(old_coll)
        
        # Create new main collection
        main_collection = bpy.data.collections.new(main_collection_name)
        
        # Link to scene collection
        bpy.context.scene.collection.children.link(main_collection)
        
        # Hide the main collection only if hide_root_collection is enabled
        if bpy.context.scene.lod_props.hide_root_collection:
            main_collection.hide_viewport = True
            main_collection.hide_render = True
        
        return main_collection

    def _create_object_lod_collection(self, original_obj, main_collection):
        """Create object's LOD collection inside main collection (no -sep suffix)"""
        # Check if object still exists
        if original_obj.name not in bpy.data.objects:
            return None
            
        base_name = self._get_base_name(original_obj.name)
        
        # Object collection name (no suffix)
        collection_name = f"{base_name}_LODs"
        
        # Remove existing collection if it exists in main
        if collection_name in main_collection.children:
            old_coll = main_collection.children[collection_name]
            # Remove all child collections first
            for child_coll in list(old_coll.children):
                bpy.data.collections.remove(child_coll)
            bpy.data.collections.remove(old_coll)
        
        # Create new object collection
        obj_collection = bpy.data.collections.new(collection_name)
        
        # Link to main collection
        main_collection.children.link(obj_collection)
        
        return obj_collection

    def _create_lod_level_collection(self, original_obj, lod_level, obj_collection):
        """Create LOD level collection with -sep suffix inside object's collection"""
        base_name = self._get_base_name(original_obj.name)
        
        # LOD level collection name with -sep
        collection_name = f"{base_name}_LOD{lod_level}-sep"
        
        # Remove existing collection if it exists in object collection
        if collection_name in obj_collection.children:
            old_coll = obj_collection.children[collection_name]
            bpy.data.collections.remove(old_coll)
        
        # Create new LOD level collection
        lod_collection = bpy.data.collections.new(collection_name)
        
        # Link to object collection
        obj_collection.children.link(lod_collection)
        
        return lod_collection

    def _process_textures(self, lod_obj, lod_level, reduction):
        # Check if object still exists
        if lod_obj.name not in bpy.data.objects:
            return
            
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
