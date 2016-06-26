import bpy

import math

from bpy_extras.io_utils import ImportHelper 
from bpy.props import StringProperty 
from bpy.types import Operator 

#parameters
reset_to_zero_on_new_scenes = False # ignore new_scene flag in log
cutoff_freq = 1.0 #Hz
kernel_size_half = 32 # 16*2+1 = 33 kernel	

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
def value_generator(filepath):
	x=0.0
	y=0.0
	r=0.0
	with open(filepath) as f:
		for line in f:
			a = line.split()
			new_scene = (len(a)>5 and a[5]=='new_scene')
			if(reset_to_zero_on_new_scenes and new_scene):
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
				#print ("kf: %d, xi: %0.1f, yi: %0.1f, dx: %0.1f, dy: %0.1f, x: %0.1f, y: %0.1f, r: %0.1f, a_rad: %f" % (int(a[0]),xi,yi,dx,dy,x,y,r, a_rad))
			kf = int(a[0])
			if (kf > 0): # correction for one-frame lag in DS log
				yield (kf-1,x,y,r,new_scene)

class windowed_sinc: # filter
	# M number of points ~4/BW; Fc - cutoff freq 0-0.5 of sampling freq
	def __init__(self,M,Fc):
		# calculate kernel
		self.k = [0] * (M+1)
		self.v = []
		self.M = M
		for i in range(0,M+1):
			if ((i-int(M/2)) == 0):
				self.k[i] = 2*math.pi*Fc
			else:
				self.k[i] = math.sin(2*math.pi*Fc * (i-M/2)) / (i-M/2)
			# window function - Blackman
			self.k[i] *= (0.42 - 0.5*math.cos(2*math.pi*i/M) + 0.08 * math.cos(4*math.pi*i/M))
		# normalize
		sum = 0		
		for i in range(0,M+1):
			sum += self.k[i]
		for i in range(0,M+1):
			self.k[i] /= sum
		# spectral inverson - make it high pass
		for i in range(0,M+1):
			self.k[i] *= -1
		self.k[int(self.M/2)] += 1
			
	def preload(self,v): # lots of same value
		self.v = [v] * self.M

	def preload_more(self,v): # additional
		self.v.append(v)
		while(len(self.v)>self.M):
			self.v.pop(0)

	def value(self,v):
		self.v.append(v)
		y = 0.0
		for i in range(0,self.M+1):
			y += self.v[i] * self.k[i]
		self.v.pop(0)
		return y
		
def filtered_value_generator_wsinc_prefetch(vg):
	max_prefetch = kernel_size_half # half of (kernel size-1)
	prefetch=0
	xf = windowed_sinc(kernel_size_half * 2,cutoff_freq/30)
	yf = windowed_sinc(kernel_size_half * 2,cutoff_freq/30)
	rf = windowed_sinc(kernel_size_half * 2,cutoff_freq/30)
	lx = 0
	ly = 0
	lr = 0
	lkf = 0
	is_head = True
	cache={}
	for (kf,x,y,r,new_scene) in vg:
		if(kf==1): # start of the file		
			xf.preload(x)
			yf.preload(y)
			rf.preload(r)
			is_head = True
		elif (reset_to_zero_on_new_scenes and new_scene):
			# offload based on the last value (should be done before next scene)
			while prefetch > 0:
				yield(kf-prefetch,xf.value(x),yf.value(ly),rf.value(lr),False)
				prefetch-=1
			# preload same value
			xf.preload(x)
			yf.preload(y)
			rf.preload(r)
			is_head = True
		if (is_head):
			if(prefetch < max_prefetch):
				xf.preload_more(x)
				yf.preload_more(y)
				rf.preload_more(r)
				prefetch+=1
			else:
				is_head=False
				yield(kf-prefetch,xf.value(x),yf.value(y),rf.value(r),False)
		else:
			yield(kf-prefetch,xf.value(x),yf.value(y),rf.value(r),False)
		lx = x
		ly = y
		lr = r
		lkf = kf
	while prefetch >= 0:
		yield(lkf-prefetch,xf.value(lx),yf.value(ly),rf.value(lr),False)
		prefetch-=1

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
		#print("x percent: %f, y percent: %f" % (x_percent, y_percent))
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
		for (kf,x,y,r,new_scene) in filtered_value_generator_wsinc_prefetch(value_generator(filepath)):
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

