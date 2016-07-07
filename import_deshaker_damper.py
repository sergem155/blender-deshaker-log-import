import bpy
#from bpy.props import *

import math

from bpy_extras.io_utils import ImportHelper 
from bpy.props import StringProperty 
from bpy.types import Operator 

#parameters
# damping factor func - 0.95 to 0.35 depending on black bars size
def damping_function(xv):
	v = abs(xv)	
	if (v>400): return 0.35
	return 0.95-(v/400)*0.6

# for rotation
def damping_function_r(xv):
	v = abs(xv)	
	if (v>15): return 0.35
	return 0.95-(v/15)*0.6

reset_to_zero_on_new_scenes = False # ignore new_scene flag in log


bl_info = {
    "name": "Import Deshaker log",
    "author": "Sergey menshikov",
    "version": (1, 1),
    "blender": (2, 65, 0),
    "location": "Sequencer -> Track View Properties",
    "description": "Load a deshaker formatted transform data into sequencer as a transform strip",
    "warning": "",
    "wiki_url": "",
    "category": "Import-Export",
}

# get values from file, translate to x y in source pixel scale and r angle
def value_generator(filepath,xdamp,ydamp,rdamp):
	x=0.0
	y=0.0
	r=0.0
	with open(filepath) as f:
		for line in f:
			a = line.split()
			new_scene = (len(a)>5 and a[5]=='new_scene')
			if(a[1]=='skipped'): continue
			if(reset_to_zero_on_new_scenes and new_scene): # ignore new scenes (option)
				x=0.0
				y=0.0
				r=0.0
			else:
				# 2D translation
				a_rad = 0 if r==0 else (r*math.pi/180)
				xi = float(a[1])
				yi = float(a[2]) * -1 # negative vertical axis
				dx = xi * math.cos(a_rad) - yi * math.sin(a_rad)
				dy = xi * math.sin(a_rad) + yi * math.cos(a_rad)
				x+=dx
				y+=dy
				r+=(-1*float(a[3]))
			x*=damping_function(x)
			y*=damping_function(y)
			r*=damping_function_r(r)
			kf = int(a[0])
			if (kf > 0): # correction for one-frame lag in DS log
				yield (kf-1,x,y,r,new_scene)

class ImportDeshaker_Class(Operator, ImportHelper): 
	"""Deshaker log format importer""" 
	bl_idname = "deshaker1.log" 
	bl_label = "Import Deshaker Format" 

	filename_ext = ".log" 
	filter_glob = StringProperty(default="*.log", options={"HIDDEN"}) 

	def execute(self, context): 
		self.import_deshaker_file(context, self.filepath) 
		#print(self.filepath)
		return {"FINISHED"} 

	def import_deshaker_file(self, context, filepath):
		# check if a scene is selected
		if(not bpy.context.screen.scene):
			self.report({'ERROR'}, "Please select an active scene with a strip in Video Sequence Editor.")
			return
		if(not bpy.context.scene.sequence_editor.active_strip):
			self.report({'ERROR'}, "Please select the strip to apply Deshaker log to.")
			return
		x_percent = 100.0 / (bpy.context.screen.scene.render.resolution_x * bpy.context.screen.scene.render.resolution_percentage / 100.0 )
		y_percent = 100.0 / (bpy.context.screen.scene.render.resolution_y * bpy.context.screen.scene.render.resolution_percentage / 100.0 )
		damp_frames = 300
		xdamp = bpy.context.screen.scene.render.resolution_x / damp_frames
		ydamp = bpy.context.screen.scene.render.resolution_y / damp_frames
		rdamp = 180 / damp_frames
		# detect context
		screen = bpy.context.window.screen
		for area in screen.areas:
			if area.type == 'SEQUENCE_EDITOR':
				break
		context = {
				'window': bpy.context.window,
				'scene': bpy.context.scene,
				'screen': screen,
				'area': area,
		}
		# create transform strip
		bpy.ops.sequencer.effect_strip_add(context,type='TRANSFORM')
		strip = bpy.context.scene.sequence_editor.active_strip
		strip.translation_unit = 'PERCENT'
		# set zero transform for frame #0
		strip.translate_start_x = 0
		strip.translate_start_y = 0
		strip.rotation_start = 0
		strip.keyframe_insert(data_path="translate_start_x", frame=0)
		strip.keyframe_insert(data_path="translate_start_y", frame=0)
		strip.keyframe_insert(data_path="rotation_start", frame=0)
		# start import
		kf = 0
		x=0.0
		y=0.0
		r=0.0
		new_scene = False
		for (kf,x,y,r,new_scene) in value_generator(filepath,xdamp,ydamp,rdamp):
			strip.translate_start_x = x * x_percent
			strip.translate_start_y = y * y_percent
			strip.rotation_start = r
			strip.keyframe_insert(data_path="translate_start_x", frame=kf)
			strip.keyframe_insert(data_path="translate_start_y", frame=kf)
			strip.keyframe_insert(data_path="rotation_start", frame=kf)


def menu_func_import(self, context): 
	self.layout.operator(ImportDeshaker_Class.bl_idname, text="Deshaker Log (.log)") 

def register(): 
	bpy.utils.register_class(ImportDeshaker_Class) 
	bpy.types.INFO_MT_file_import.append(menu_func_import) 

def unregister(): 
	bpy.utils.unregister_class(ImportDeshaker_Class) 
	bpy.types.INFO_MT_file_import.remove(menu_func_import) 

if __name__ == "__main__": 
	register()

