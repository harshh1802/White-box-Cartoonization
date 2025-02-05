from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
import cv2
import numpy as np
import tensorflow as tf
import tensorflow.compat.v1 as v1
tf.compat.v1.disable_eager_execution()
from pathlib import Path
import io
import network
import guided_filter
from tempfile import NamedTemporaryFile 
import uuid
import time



def generate_random_filename(extension=".png"):
    timestamp = int(time.time())
    unique_id = str(uuid.uuid4().hex)[:8]  # Using first 8 characters of UUID
    filename = f"{timestamp}_{unique_id}{extension}"
    return filename

model_path = r"./saved_models/"

app = FastAPI()

def resize_crop(image):
    h, w, c = np.shape(image)
    if min(h, w) > 720:
        if h > w:
            h, w = int(720*h/w), 720
        else:
            h, w = 720, int(720*w/h)
    image = cv2.resize(image, (w, h), interpolation=cv2.INTER_AREA)
    h, w = (h//8)*8, (w//8)*8
    image = image[:h, :w, :]
    return image

def cartoonize_image(image):
    input_photo = v1.placeholder(tf.float32, [1, None, None, 3])
    network_out = network.unet_generator(input_photo)
    final_out = guided_filter.guided_filter(input_photo, network_out, r=1, eps=5e-3)

    all_vars = tf.compat.v1.trainable_variables()
    gene_vars = [var for var in all_vars if 'generator' in var.name]
    saver = tf.compat.v1.train.Saver(var_list=gene_vars)

    config = tf.compat.v1.ConfigProto()
    config.gpu_options.allow_growth = True
    sess = tf.compat.v1.Session(config=config)

    sess.run(tf.compat.v1.global_variables_initializer())
    saver.restore(sess, tf.compat.v1.train.latest_checkpoint(model_path))

    batch_image = image.astype(np.float32)/127.5 - 1
    batch_image = np.expand_dims(batch_image, axis=0)
    output = sess.run(final_out, feed_dict={input_photo: batch_image})
    output = (np.squeeze(output)+1)*127.5
    output = np.clip(output, 0, 255).astype(np.uint8)

    return output

@app.post("/cartoonize/")
async def cartoonize_endpoint(file: UploadFile = File(...)):
    try:
        content = await file.read()
        nparr = np.frombuffer(content, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        image = resize_crop(image)
        
        with tf.compat.v1.Graph().as_default():
            output_image = cartoonize_image(image)

        _, output_buffer = cv2.imencode(".png", output_image)
        
        # with NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
        #     temp_file.write(output_buffer)

        random_file_name = generate_random_filename()

        with open(random_file_name, "wb") as file:
            file.write(output_buffer)

        # Clear TensorFlow default session and graph
        tf.compat.v1.keras.backend.clear_session()
        tf.compat.v1.reset_default_graph()


        # return FileResponse(temp_file.name, media_type="image/png")
        return random_file_name
    except Exception as e:
        return {"error": str(e)}

@app.get("/file/{file_name}")
async def cartoonize_endpoint(file_name):
    try:
        return FileResponse(file_name, media_type="image/png")
    except:
        return "NO File"

