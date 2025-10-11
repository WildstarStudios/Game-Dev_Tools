import bpy
import math
from mathutils import Euler, Vector
from bpy.props import FloatVectorProperty, BoolProperty, FloatProperty
import time

bl_info = {
    "name": "Viewport Navigator",
    "author": "Your Name",
    "version": (1, 3),
    "blender": (3, 0, 0),
    "location": "3D View > Sidebar > View",
    "description": "Real-time viewport position and rotation control",
    "category": "3D View",
}

# Global variables
updating = False
last_update_time = 0
update_interval = 0.1  # seconds
handler_active = False

def get_active_view_3d():
    """Safely get active 3D view region data"""
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            return space.region_3d
        return None
    except:
        return None

def update_viewport_from_properties():
    """Update viewport when properties change"""
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
    
    # Apply new rotation
    try:
        rot_euler = Euler((
            math.radians(wm.viewport_rotation[0]),
            math.radians(wm.viewport_rotation[1]),
            math.radians(wm.viewport_rotation[2])
        ), 'XYZ')
        r3d.view_rotation = rot_euler.to_quaternion()
    except:
        pass
    
    # Apply new location
    try:
        r3d.view_location = wm.viewport_location
    except:
        pass
    
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
        # Convert quaternion to Euler (degrees)
        rot_euler = r3d.view_rotation.to_euler('XYZ')
        rotation_degrees = (
            math.degrees(rot_euler.x),
            math.degrees(rot_euler.y),
            math.degrees(rot_euler.z)
        )
        
        # Update properties if different
        if (rotation_degrees != wm.viewport_rotation or 
            r3d.view_location != wm.viewport_location):
            updating = True
            wm.viewport_location = r3d.view_location
            wm.viewport_rotation = rotation_degrees
            updating = False
    except:
        pass
        
    last_update_time = current_time

def viewport_update_timer():
    """Timer callback for viewport updates"""
    global handler_active
    try:
        if bpy.context.window_manager.enable_viewport_control:
            update_properties_from_viewport()
    except:
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
            
            col = layout.column(align=True)
            col.label(text="Viewport Location:")
            col.prop(wm, "viewport_location", text="")
            
            col = layout.column(align=True)
            col.label(text="Viewport Rotation (Degrees):")
            col.prop(wm, "viewport_rotation", text="")
            
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
        
        # Initialize properties
        r3d = get_active_view_3d()
        if r3d:
            rot_euler = r3d.view_rotation.to_euler('XYZ')
            wm.viewport_rotation = (
                math.degrees(rot_euler.x),
                math.degrees(rot_euler.y),
                math.degrees(rot_euler.z)
            )
            wm.viewport_location = r3d.view_location
        
        # Start timer if not already running
        global handler_active
        if not handler_active:
            bpy.app.timers.register(viewport_update_timer, persistent=True)
            handler_active = True
            
        return {'FINISHED'}

class VIEW3D_OT_reset_viewport_transform(bpy.types.Operator):
    bl_idname = "viewport.reset_transform"
    bl_label = "Reset Viewport"
    bl_description = "Reset viewport to origin"
    
    def execute(self, context):
        wm = context.window_manager
        wm.viewport_location = (0.0, 0.0, 0.0)
        wm.viewport_rotation = (0.0, 0.0, 0.0)
        update_viewport_from_properties()
        return {'FINISHED'}

def register():
    bpy.utils.register_class(VIEW3D_PT_viewport_navigator)
    bpy.utils.register_class(VIEW3D_OT_activate_control)
    bpy.utils.register_class(VIEW3D_OT_reset_viewport_transform)
    
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
    
    WindowManager.enable_viewport_control = BoolProperty(
        name="Enable Control",
        default=False
    )
    
    # Initialize properties
    wm = bpy.context.window_manager
    wm.viewport_location = (0.0, 0.0, 0.0)
    wm.viewport_rotation = (0.0, 0.0, 0.0)
    wm.enable_viewport_control = False

def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_viewport_navigator)
    bpy.utils.unregister_class(VIEW3D_OT_activate_control)
    bpy.utils.unregister_class(VIEW3D_OT_reset_viewport_transform)
    
    # Stop timer if running
    global handler_active
    if handler_active:
        bpy.app.timers.unregister(viewport_update_timer)
        handler_active = False
    
    del bpy.types.WindowManager.viewport_location
    del bpy.types.WindowManager.viewport_rotation
    del bpy.types.WindowManager.enable_viewport_control

if __name__ == "__main__":
    register()
