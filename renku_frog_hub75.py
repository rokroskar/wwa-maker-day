import rp2
import time
from machine import Pin
import array
import math
import _thread
import random

#TODO
#* work out how to place pixels in different places
#* buffering??

clock_pin = 11
data_pin_start = 0
latch_pin_start = 12
row_pin_start = 6

row_bits = 3
data_bits = 192 # note must be divisible by 32

row_ar_len = 50

@rp2.asm_pio(out_shiftdir=1, autopull=True, pull_thresh=24, out_init=(rp2.PIO.OUT_HIGH, rp2.PIO.OUT_LOW, rp2.PIO.OUT_HIGH,
                                                                    rp2.PIO.OUT_HIGH, rp2.PIO.OUT_HIGH, rp2.PIO.OUT_HIGH), sideset_init=(rp2.PIO.OUT_LOW))
def data_hub75():
    #pull # actually, can I use autopull?
    #is this a bit weird? better to use nops with side set?
    #really simple clocking out of pins?
    #not 100% sure how this will work as pulling in 32 bits at a time, but out won't line up with this?
    #do I need some dummy bits?
    #wrap_target()
    
    #nop() .side(0)
    out(pins, 6)
    nop()        .side(1)
    nop()        .side(0)
    out(pins, 6)
    nop()        .side(1)
    nop()        .side(0)
    out(pins, 6)
    nop()        .side(1)
    nop()        .side(0)
    out(pins, 6)
    nop()        .side(1)
    nop()        .side(0)
    #wrap()
    
@rp2.asm_pio(out_shiftdir=1, autopull=False,out_init=(rp2.PIO.OUT_LOW,rp2.PIO.OUT_LOW,rp2.PIO.OUT_LOW,
            rp2.PIO.OUT_LOW,rp2.PIO.OUT_LOW), sideset_init=(rp2.PIO.OUT_LOW, rp2.PIO.OUT_LOW))

def row_hub75():
    wrap_target()
    pull()
    
    nop()     .side(2) 
    out(pins, 5)   [2]#note 3 as only three pins needed for 32x32 screen. This might be wrong. Might needs all five still
    nop()      .side(3) #this triggers the latch
    nop()      .side(2) #this disables the latch
    nop()      .side(0) 
    

#setup state machines
#can I run them at full tilt, or do they need slowing down?
sm_data = rp2.StateMachine(0, data_hub75, out_base=Pin(data_pin_start), sideset_base=Pin(clock_pin), freq=20000000)#55000000)
sm_row = rp2.StateMachine(1, row_hub75, out_base=Pin(row_pin_start), sideset_base=Pin(latch_pin_start), freq=20000000)#1000000)
    
sm_row.active(1)
sm_data.active(1)

counter = 0

toggle = False

rows = []
blocks_per_row = const(16) #each block has 24 bits, so 4 pixels x 2 scanlines
num_rows = const(16)

fast_buffer1 = array.array("I")
fast_buffer2 = array.array("I")
for i in range(blocks_per_row * num_rows):
    fast_buffer1.append(0)
    fast_buffer2.append(0)
drawBuffer = fast_buffer1
frameBuffer = fast_buffer2

#fill with white
# for j in range(num_rows):
#     rows.append([])
#     for i in range(blocks_per_row):
#         rows[j].append(0xffffffff)


#fill with black
for j in range(num_rows):
    rows.append([])
    for i in range(blocks_per_row):
        rows[j].append(0x00000000)

# There are 32x32 3-bit values for each panel.
# Pins r1g1b1 control scanlines 0-15 while pins r2g2b2 control scanlines 16-31
# We want to write 24-bits at a time so we can write out 4 pixels per scanline at a time
# 1st pixel 0th scanline would be the lowest bits (0-2)
# 1st pixel 16th scanline would be the next bits (3-5)
# 2nd pixel 0th scanline would be the next lowest bits (6-8)
# 2nd pixel 16th scanline would be the next lowest bits (9-11)
# continue this pattern to fill our 24-bits

@micropython.viper
def set_pixel(x:int, y:int, rgb:uint):

    bit_posn = ((x % 4) * 6)
    if y > 15:
        y = y - 17
        bit_posn += 3
    else:
        y = y - 1

    # a mystery but rows 0/16 need to use y = 15 to be drawn correctly
    if y == -1:
        y = 15

    index = y * blocks_per_row + int(x >> 2)
    val = uint(drawBuffer[index])

    drawBuffer[index] = val | uint(rgb << (bit_posn))
        
def light_xy(x,y, r, g, b):
    rgb = (r << 0) | (g << 1) | (b << 2);
    set_pixel(x, y, rgb)
    
#p-shape
#should these really be stored as datapoints?
def p_draw(init_x, init_y, r, g, b):
    #line 10 pixels high
    for i in range(10):
        light_xy(init_x, init_y+i, r, g, b)
    #line 4 pixesl across
    for i in range(4):
        light_xy(init_x+i, init_y, r, g, b)
    for i in range(4):
        light_xy(init_x+i, init_y+4, r, g, b)
    for i in range(3):
        light_xy(init_x+4, init_y+i+1, r, g, b)
        
def i_draw(init_x, init_y, r, g, b):
    for i in range(4):
        light_xy(init_x, init_y+i+2, r, g, b)
    light_xy(init_x, init_y, r, g, b)
    
def c_draw(init_x, init_y, r, g, b):
    for i in range(4):
        light_xy(init_x, init_y+i+1, r, g, b)
    for i in range(3):
        light_xy(init_x+1+i, init_y, r, g, b)
        light_xy(init_x+1+i, init_y+5, r, g, b)
        
def o_draw(init_x, init_y, r, g, b):
    for i in range(4):
        light_xy(init_x, init_y+i+1, r, g, b)
        light_xy(init_x+4, init_y+i+1, r, g, b)
    for i in range(3):
        light_xy(init_x+1+i, init_y, r, g, b)
        light_xy(init_x+1+i, init_y+5, r, g, b)

def clearBuffer():
    # reusing should be same or faster than reallocations
    #for j in range(num_rows):
    #    for i in range(blocks_per_row):
    #        rows[j][i] = 0

    for i in range(num_rows * blocks_per_row):
         drawBuffer[i] = 0

text_y = 14
direction = 1

def draw_text():
    global text_y
    global direction
    global writing
    global current_rows
    global rows
    
    writing = True
    text_y = text_y + direction
    if text_y > 25: direction = -0.1
    if text_y < 5: direction = 0.1
#     text_y = 14

    clearBuffer()
            
    p_draw(3, int(text_y)-4, 1, 1, 1)
    i_draw(9, int(text_y), 1, 1, 0)
    c_draw(11, int(text_y), 0, 1, 1)
    o_draw(16, int(text_y), 1, 0, 1)
    writing = False
    
#draw_text()
draw_counter = 0

writing = False

out_rows = rows

def draw_performance():
    global writing
    global rows

    writing = True

    start = time.ticks_us()

    counter = random.randint(1, 7);

    clearBuffer()

    for j in range(32):
        for i in range(32):
            set_pixel(i, j, 1 + counter % 6)
            counter += 1

    end = time.ticks_us()
    usecs = time.ticks_diff(end, start)
    print(usecs / 1000.0)

    writing = False

def draw_test_pattern():
    global writing
    global rows

    writing = True

    clearBuffer()

    for i in range(0,32):
        # draw random selection of rows/colums using all colors
        light_xy(i, 31, 0, 0, 1)
        light_xy(i, 0, 0, 1, 0)
        light_xy(i, 16, 0, 1, 1)
        light_xy(0, i, 1, 0, 0)
        light_xy(5, i, 1, 0, 1)
        light_xy(15, i, 1, 1, 0)
        light_xy(25, i, 1, 1, 1)
        light_xy(30, i, 1, 0, 0)

    writing = False
    

frog = [
  ["b","b","b","b","b","g","b","b","b","b","b","b","b"],
  ["b","g","b","b","g","g","g","b","b","b","b","b","b"],
  ["g","g","g","b","b","g","b","b","r","g","b","b","b"],
  ["b","g","b","b","b","g","b","g","g","g","g","b","b"],
  ["b","g","g","g","b","g","g","g","g","g","r","b","b"],
  ["b","b","b","g","b","g","g","g","g","g","b","b","b"],
  ["b","b","b","g","g","g","g","g","g","b","b","b","b"],
  ["b","b","b","g","g","g","g","g","g","b","b","g","b"],
  ["b","b","b","b","g","g","g","b","g","g","g","g","g"],
  ["b","b","b","b","b","g","g","b","b","b","b","g","b"],
  ["b","b","g","g","g","g","g","g","b","b","b","b","b"],
  ["b","g","g","g","b","b","b","b","b","b","b","b","b"],
  ["b","b","g","b","b","b","b","b","b","b","b","b","b"],
]

text_y = 8
direction = 0.1

text_x = 12
direction_x = 0.2

def draw_frog():
    global writing
    global rows
    global frog
    global text_y
    global direction
    global text_x
    global direction_x
    
    writing = True
    clearBuffer()
    
    text_y = text_y + direction
    if text_y > 19: direction = -0.1
    if text_y < 0: direction = 0.1
    
    text_x = text_x + direction_x
    if text_x > 51: direction_x = -0.1
    if text_x < 0: direction_x = 0.1
    
    for y, f_col in enumerate(frog):
        for x, c in enumerate(f_col):
            xx = int(text_x) + x
            yy = int(text_y) + y
            
            if c == "g":
                light_xy(xx, yy, 0, 1, 0)
            if c == "r":
                light_xy(xx, yy, 1, 0, 1)
    
    writing = False

# draw_test_pattern()

while True:
#     draw_test_pattern()
# 
    sm_row.put(counter)

    # Write out 8 integers that hold 8 pixels worth of 3-bit RGB (two scanlines x four pixels)
    baseIndex = counter * 16
    for i in range(16):
        val = frameBuffer[baseIndex + i]
        sm_data.put(val)
        #sm_data.put(out_rows[counter][i])

    counter += 1
    if (counter > 15):
        counter = 0
        if writing == False:

            # perform our double buffering
            tempBuffer = frameBuffer
            frameBuffer = drawBuffer
            drawBuffer = tempBuffer
            _thread.start_new_thread(draw_frog, ())
