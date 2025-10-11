import bpy
import math
from mathutils import Euler, Vector
from bpy.props import FloatVectorProperty, BoolProperty, FloatProperty
import time

bl_info = {
    "name": "Viewport Navigator",
    "author": "WildStar Studios",
    "version": (1, 0),
    "blender": (4, 5, 0),
    "location": "3D View > Sidebar > View",
    "description": "Real-time viewport position, rotation and zoom control",
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
    
    # Apply new zoom (view distance)
    try:
        # In Blender, smaller view_distance = more zoom
        r3d.view_distance = wm.viewport_zoom
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
        location_changed = r3d.view_location != wm.viewport_location
        rotation_changed = rotation_degrees != wm.viewport_rotation
        zoom_changed = r3d.view_distance != wm.viewport_zoom
        
        if location_changed or rotation_changed or zoom_changed:
            updating = True
            wm.viewport_location = r3d.view_location
            wm.viewport_rotation = rotation_degrees
            wm.viewport_zoom = r3d.view_distance
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
            
            # Location
            col = layout.column(align=True)
            col.label(text="Location:")
            col.prop(wm, "viewport_location", text="")
            
            # Rotation
            col = layout.column(align=True)
            col.label(text="Rotation (Degrees):")
            col.prop(wm, "viewport_rotation", text="")
            
            # Zoom
            col = layout.column(align=True)
            col.label(text="Zoom (Distance):")
            row = col.row(align=True)
            row.prop(wm, "viewport_zoom", text="", slider=True)
            row.operator("viewport.zoom_in", text="", icon='ZOOM_IN')
            row.operator("viewport.zoom_out", text="", icon='ZOOM_OUT')
            
            # Reset buttons
            row = layout.row(align=True)
            row.operator("viewport.reset_transform", icon='LOOP_BACK')
            row.operator("viewport.reset_zoom", text="Reset Zoom")
            
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
        # Set a reasonable default zoom value
        wm.viewport_zoom = 10.0
        update_viewport_from_properties()
        return {'FINISHED'}

class VIEW3D_OT_zoom_in(bpy.types.Operator):
    bl_idname = "viewport.zoom_in"
    bl_label = "Zoom In"
    bl_description = "Zoom in (decrease view distance)"
    
    def execute(self, context):
        wm = context.window_manager
        # Smaller value = more zoom
        wm.viewport_zoom = max(0.1, wm.viewport_zoom * 0.8)
        update_viewport_from_properties()
        return {'FINISHED'}

class VIEW3D_OT_zoom_out(bpy.types.Operator):
    bl_idname = "viewport.zoom_out"
    bl_label = "Zoom Out"
    bl_description = "Zoom out (increase view distance)"
    
    def execute(self, context):
        wm = context.window_manager
        # Larger value = less zoom
        wm.viewport_zoom = min(1000.0, wm.viewport_zoom * 1.25)
        update_viewport_from_properties()
        return {'FINISHED'}

def register():
    bpy.utils.register_class(VIEW3D_PT_viewport_navigator)
    bpy.utils.register_class(VIEW3D_OT_activate_control)
    bpy.utils.register_class(VIEW3D_OT_reset_viewport_transform)
    bpy.utils.register_class(VIEW3D_OT_reset_zoom)
    bpy.utils.register_class(VIEW3D_OT_zoom_in)
    bpy.utils.register_class(VIEW3D_OT_zoom_out)
    
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
    
    # Initialize properties
    wm = bpy.context.window_manager
    wm.viewport_location = (0.0, 0.0, 0.0)
    wm.viewport_rotation = (0.0, 0.0, 0.0)
    wm.viewport_zoom = 10.0
    wm.enable_viewport_control = False

def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_viewport_navigator)
    bpy.utils.unregister_class(VIEW3D_OT_activate_control)
    bpy.utils.unregister_class(VIEW3D_OT_reset_viewport_transform)
    bpy.utils.unregister_class(VIEW3D_OT_reset_zoom)
    bpy.utils.unregister_class(VIEW3D_OT_zoom_in)
    bpy.utils.unregister_class(VIEW3D_OT_zoom_out)
    
    # Stop timer if running
    global handler_active
    if handler_active:
        bpy.app.timers.unregister(viewport_update_timer)
        handler_active = False
    
    del bpy.types.WindowManager.viewport_location
    del bpy.types.WindowManager.viewport_rotation
    del bpy.types.WindowManager.viewport_zoom
    del bpy.types.WindowManager.enable_viewport_control

if __name__ == "__main__":
    register()
