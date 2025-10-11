import bpy
import math
from mathutils import Euler
from bpy.props import FloatVectorProperty, BoolProperty, FloatProperty, PointerProperty
from bpy.types import PropertyGroup, Scene
import time

bl_info = {
    "name": "Viewport Navigator",
    "author": "WildStar Studios",
    "version": (1, 1),
    "blender": (4, 5, 0),
    "location": "3D View > Sidebar > View",
    "description": "Viewport control with sensitivity adjustment",
    "category": "3D View",
}

# Global variables
updating = False
last_update_time = 0
update_interval = 0.1  # seconds
handler_active = False

# Property group for blend-file stored settings
class ViewportNavigatorSettings(PropertyGroup):
    rotation_sensitivity: FloatProperty(
        name="Rotation Sensitivity",
        description="Multiplier for rotation sensitivity. Higher = faster rotation",
        default=10.0,
        min=0.1,
        max=50.0
    )

def get_active_view_3d():
    """Safely get active 3D view region data"""
    try:
        # Use context directly for better reliability
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        return space.region_3d
        return None
    except:
        return None

def update_viewport_from_properties():
    """Update viewport when properties change with adjustable sensitivity"""
    global updating
    if updating:
        return

    wm = bpy.context.window_manager
    if not wm.enable_viewport_control:
        return

    r3d = get_active_view_3d()
    if not r3d:
        return

    updating = True
    
    # Get scene settings
    scene = bpy.context.scene
    vn_settings = scene.viewport_navigator_settings
    
    # Apply new rotation with adjustable sensitivity
    try:
        rot_euler = Euler((
            math.radians(wm.viewport_rotation[0] * vn_settings.rotation_sensitivity),
            math.radians(wm.viewport_rotation[1] * vn_settings.rotation_sensitivity), 
            math.radians(wm.viewport_rotation[2] * vn_settings.rotation_sensitivity)
        ), 'XYZ')
        r3d.view_rotation = rot_euler.to_quaternion()
    except Exception as e:
        print(f"Rotation error: {e}")
    
    # Apply new location
    try:
        r3d.view_location = wm.viewport_location
    except Exception as e:
        print(f"Location error: {e}")
    
    # Apply new zoom
    try:
        r3d.view_distance = wm.viewport_zoom
    except Exception as e:
        print(f"Zoom error: {e}")
    
    updating = False

def update_properties_from_viewport():
    """Update properties when viewport changes"""
    global updating, last_update_time
    current_time = time.time()
    
    # Throttle updates to prevent performance issues
    if current_time - last_update_time < update_interval:
        return
        
    if updating:
        return

    wm = bpy.context.window_manager
    if not wm.enable_viewport_control:
        return

    r3d = get_active_view_3d()
    if not r3d:
        return

    try:
        # Get scene settings
        scene = bpy.context.scene
        vn_settings = scene.viewport_navigator_settings
        
        # Convert quaternion to Euler (degrees with sensitivity adjustment)
        rot_euler = r3d.view_rotation.to_euler('XYZ')
        rotation_degrees = (
            math.degrees(rot_euler.x) / vn_settings.rotation_sensitivity,
            math.degrees(rot_euler.y) / vn_settings.rotation_sensitivity,
            math.degrees(rot_euler.z) / vn_settings.rotation_sensitivity
        )
        
        # Update all properties
        updating = True
        wm.viewport_location = r3d.view_location
        wm.viewport_rotation = rotation_degrees
        wm.viewport_zoom = r3d.view_distance
        updating = False
        
    except Exception as e:
        print(f"Update properties error: {e}")
        
    last_update_time = current_time

def viewport_update_timer():
    """Timer callback for viewport updates"""
    global handler_active
    try:
        # Safe context access to avoid RestrictContext errors
        if hasattr(bpy.context, 'window_manager') and bpy.context.window_manager.enable_viewport_control:
            update_properties_from_viewport()
    except Exception as e:
        print(f"Timer error: {e}")
        # Clean up if context becomes invalid
        bpy.app.timers.unregister(viewport_update_timer)
        handler_active = False
        return None
    
    return update_interval

class VIEW3D_PT_viewport_navigator(bpy.types.Panel):
    bl_label = "Viewport Navigator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'View'

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        
        if not wm.enable_viewport_control:
            layout.operator("viewport.activate_control", text="Activate", icon='PLAY')
        else:
            layout.prop(wm, "enable_viewport_control", toggle=True, text="Deactivate")
            
            # Get scene settings
            scene = context.scene
            vn_settings = scene.viewport_navigator_settings
            
            # Sensitivity Settings - stored in scene
            box = layout.box()
            box.label(text="Sensitivity Settings:", icon='PREFERENCES')
            box.prop(vn_settings, "rotation_sensitivity", slider=True)
            box.label(text=f"Current: {vn_settings.rotation_sensitivity}x")
            box.label(text="Saved in .blend file", icon='FILE_BLEND')
            
            # Location
            col = layout.column(align=True)
            col.label(text="Location:")
            col.prop(wm, "viewport_location", text="")
            
            # Rotation
            col = layout.column(align=True)
            col.label(text="Rotation (Adjusted by Sensitivity):")
            col.prop(wm, "viewport_rotation", text="")
            
            # Zoom
            col = layout.column(align=True)
            col.label(text="Zoom (Distance):")
            row = col.row(align=True)
            row.prop(wm, "viewport_zoom", text="", slider=True)
            
            row = col.row(align=True)
            row.operator("viewport.zoom_in", text="", icon='ZOOM_IN')
            row.operator("viewport.zoom_out", text="", icon='ZOOM_OUT')
            row.operator("viewport.reset_zoom", text="Reset Zoom")
            
            # Reset button
            layout.operator("viewport.reset_transform", icon='LOOP_BACK')
            
            # Add warning if no active 3D view
            if not get_active_view_3d():
                layout.label(text="No active 3D view found!", icon='ERROR')

class VIEW3D_OT_activate_control(bpy.types.Operator):
    bl_idname = "viewport.activate_control"
    bl_label = "Activate Control"
    bl_description = "Activate viewport tracking"
    
    def execute(self, context):
        wm = context.window_manager
        wm.enable_viewport_control = True
        
        # Initialize properties with CURRENT viewport state, not defaults
        r3d = get_active_view_3d()
        if r3d:
            # Get scene settings for sensitivity
            scene = context.scene
            vn_settings = scene.viewport_navigator_settings
            
            rot_euler = r3d.view_rotation.to_euler('XYZ')
            wm.viewport_rotation = (
                math.degrees(rot_euler.x) / vn_settings.rotation_sensitivity,
                math.degrees(rot_euler.y) / vn_settings.rotation_sensitivity,
                math.degrees(rot_euler.z) / vn_settings.rotation_sensitivity
            )
            wm.viewport_location = r3d.view_location
            wm.viewport_zoom = r3d.view_distance
        
        # Start timer if not already running
        global handler_active
        if not handler_active:
            bpy.app.timers.register(viewport_update_timer, persistent=True)
            handler_active = True
            
        return {'FINISHED'}

class VIEW3D_OT_reset_viewport_transform(bpy.types.Operator):
    bl_idname = "viewport.reset_transform"
    bl_label = "Reset Transform"
    bl_description = "Reset viewport location and rotation to origin"
    
    def execute(self, context):
        wm = context.window_manager
        wm.viewport_location = (0.0, 0.0, 0.0)
        wm.viewport_rotation = (0.0, 0.0, 0.0)
        update_viewport_from_properties()
        return {'FINISHED'}

class VIEW3D_OT_reset_zoom(bpy.types.Operator):
    bl_idname = "viewport.reset_zoom"
    bl_label = "Reset Zoom"
    bl_description = "Reset zoom to default value"
    
    def execute(self, context):
        wm = context.window_manager
        wm.viewport_zoom = 10.0
        update_viewport_from_properties()
        return {'FINISHED'}

class VIEW3D_OT_zoom_in(bpy.types.Operator):
    bl_idname = "viewport.zoom_in"
    bl_label = "Zoom In"
    bl_description = "Zoom in (decrease view distance)"
    
    def execute(self, context):
        wm = context.window_manager
        wm.viewport_zoom = max(0.1, wm.viewport_zoom * 0.8)
        update_viewport_from_properties()
        return {'FINISHED'}

class VIEW3D_OT_zoom_out(bpy.types.Operator):
    bl_idname = "viewport.zoom_out"
    bl_label = "Zoom Out"
    bl_description = "Zoom out (increase view distance)"
    
    def execute(self, context):
        wm = context.window_manager
        wm.viewport_zoom = min(1000.0, wm.viewport_zoom * 1.25)
        update_viewport_from_properties()
        return {'FINISHED'}

# Registration
classes = (
    ViewportNavigatorSettings,
    VIEW3D_PT_viewport_navigator,
    VIEW3D_OT_activate_control,
    VIEW3D_OT_reset_viewport_transform,
    VIEW3D_OT_reset_zoom,
    VIEW3D_OT_zoom_in,
    VIEW3D_OT_zoom_out,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Scene properties for blend-file storage
    bpy.types.Scene.viewport_navigator_settings = PointerProperty(type=ViewportNavigatorSettings)
    
    # Window manager properties for real-time control
    WindowManager = bpy.types.WindowManager
    
    WindowManager.viewport_location = FloatVectorProperty(
        name="Location",
        subtype='TRANSLATION',
        size=3,
        default=(0.0, 0.0, 0.0),
        update=lambda self, context: update_viewport_from_properties()
    )
    
    WindowManager.viewport_rotation = FloatVectorProperty(
        name="Rotation",
        subtype='EULER', 
        size=3,
        default=(0.0, 0.0, 0.0),
        update=lambda self, context: update_viewport_from_properties()
    )
    
    WindowManager.viewport_zoom = FloatProperty(
        name="Zoom",
        description="Viewport zoom (distance). Lower values = more zoom",
        default=10.0,
        min=0.1,
        max=1000.0,
        update=lambda self, context: update_viewport_from_properties()
    )
    
    WindowManager.enable_viewport_control = BoolProperty(
        name="Enable Control",
        default=False
    )
    
    # Initialize with current viewport state when first enabled
    wm = bpy.context.window_manager
    wm.enable_viewport_control = False

def unregister():
    # Stop timer if running
    global handler_active
    if handler_active:
        bpy.app.timers.unregister(viewport_update_timer)
        handler_active = False
    
    # Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    # Remove properties
    del bpy.types.Scene.viewport_navigator_settings
    
    WindowManager = bpy.types.WindowManager
    props_to_remove = [
        'viewport_location', 'viewport_rotation', 'viewport_zoom',
        'enable_viewport_control'
    ]
    
    for prop in props_to_remove:
        if hasattr(WindowManager, prop):
            delattr(WindowManager, prop)

if __name__ == "__main__":
    register()
