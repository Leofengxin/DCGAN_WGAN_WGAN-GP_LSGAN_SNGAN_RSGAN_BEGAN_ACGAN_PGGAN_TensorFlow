import tensorflow as tf
import numpy as np
import os
from PIL import Image
import scipy.misc as misc


def mapping(img):
    max = np.max(img)
    min = np.min(img)
    return (img - min) * 255.0 / (max - min + 1e-5)

def leaky_relu(x, alpha=0.2):
    return tf.maximum(x, alpha*x)

def conv2d(name, x, out_nums, ksize, strides, padding="SAME"):
    c = int(np.shape(x)[3])
    kernel = tf.get_variable(name+"weight", shape=[ksize, ksize, c, out_nums], initializer=tf.random_normal_initializer(mean=0., stddev=0.02))
    bias = tf.get_variable(name+"bias", shape=[out_nums], initializer=tf.constant_initializer(0.))
    return tf.nn.conv2d(x, kernel, [1, strides, strides, 1], padding) + bias

def deconv2d(name, x, out_nums, ksize, strides, padding="SAME"):
    b = tf.shape(x)[0]
    w = x.shape[2]
    h = x.shape[1]
    c = x.shape[3]
    kernel = tf.get_variable(name + "weight", shape=[ksize, ksize, out_nums, c], initializer=tf.random_normal_initializer(mean=0., stddev=0.02))
    bias = tf.get_variable(name + "bias", shape=[out_nums], initializer=tf.constant_initializer(0.))
    return tf.nn.conv2d_transpose(x, kernel, [b, h*strides, w*strides, out_nums], [1, strides, strides, 1], padding=padding)+bias

def instanceNorm(name, inputs):
    with tf.variable_scope(name):
        mean, var = tf.nn.moments(inputs, axes=[1, 2], keep_dims=True)
        scale = tf.get_variable("scale", shape=mean.shape[-1], initializer=tf.constant_initializer([1.]))
        shift = tf.get_variable("shift", shape=mean.shape[-1], initializer=tf.constant_initializer([0.]))
    return (inputs - mean) * scale / tf.sqrt(var + 1e-8) + shift

def fully_connected(name, x, out_nums=1):
    x_flatten = tf.layers.flatten(x)
    W = tf.get_variable(name+"weight", shape=[int(np.shape(x_flatten)[1]), out_nums], initializer=tf.random_normal_initializer(stddev=0.02))
    b = tf.get_variable(name+"bias", shape=[out_nums], initializer=tf.random_normal_initializer(stddev=0.02))
    return tf.matmul(x_flatten, W) + b



class pix2pix():
    def __init__(self, batchsize=4, img_h=256, img_w=256, lambda_l1=100, path="./dataset/maps/train/"):
        self.batch_size = batchsize
        self.img_h = img_h
        self.img_w = img_w
        self.lambda_l1 = lambda_l1
        self.path = path
        self.inputs = tf.placeholder("float", [None, self.img_h, self.img_w, 3])
        self.inputs_condition = tf.placeholder("float", [None, self.img_h, self.img_w, 3])
        self.inputs_fake = self.generator(self.inputs_condition)
        self.logit_real = self.discriminator(self.inputs, self.inputs_condition)
        self.logit_fake = self.discriminator(self.inputs_fake, self.inputs_condition)
        self.d_loss = tf.reduce_mean(tf.nn.sigmoid(self.logit_fake - self.logit_real))
        self.g_loss = tf.reduce_mean(tf.nn.sigmoid(self.logit_real - self.logit_fake))
        self.l1_loss = tf.reduce_mean(tf.abs(self.inputs_fake - self.inputs))
        self.g_loss += self.lambda_l1 * self.l1_loss
        self.opt_dis = tf.train.AdamOptimizer(2e-4, beta1=0., beta2=0.9).minimize(self.d_loss, var_list=tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, "discriminator"))
        self.opt_gen = tf.train.AdamOptimizer(2e-4, beta1=0., beta2=0.9).minimize(self.g_loss, var_list=tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, "generator"))
        self.sess = tf.Session()
        self.sess.run(tf.global_variables_initializer())
        self.train()


    def train(self):

        list = os.listdir(self.path)
        nums_file = list.__len__()
        saver = tf.train.Saver()
        for i in range(10000):
            rand_select = np.random.randint(0, nums_file, [self.batch_size])
            INPUTS = np.zeros([self.batch_size, self.img_h, self.img_w, 3])
            INPUTS_CONDITION = np.zeros([self.batch_size, self.img_h, self.img_w, 3])
            for j in range(self.batch_size):
                img = np.array(Image.open(self.path + list[rand_select[j]]))
                img_h, img_w = img.shape[0], img.shape[1]
                INPUTS_CONDITION[j] = misc.imresize(img[:, :img_w//2], [self.img_h, self.img_w]) / 127.5 - 1.0
                INPUTS[j] = misc.imresize(img[:, img_w//2:], [self.img_h, self.img_w]) / 127.5 - 1.0
            self.sess.run(self.opt_dis, feed_dict={self.inputs: INPUTS, self.inputs_condition: INPUTS_CONDITION})
            self.sess.run(self.opt_gen, feed_dict={self.inputs: INPUTS, self.inputs_condition: INPUTS_CONDITION})
            if i % 10 == 0:
                [G_LOSS, D_LOSS] = self.sess.run([self.g_loss, self.d_loss], feed_dict={self.inputs: INPUTS, self.inputs_condition: INPUTS_CONDITION})
                print("Iteration: %d, d_loss: %f, g_loss: %f"%(i, D_LOSS, G_LOSS))
            if i % 100 == 0:
                saver.save(self.sess, "./save_para//model.ckpt")

    def discriminator(self, inputs, inputs_condition):
        inputs = tf.concat([inputs, inputs_condition], axis=3)
        inputs = tf.random_crop(inputs, [1, 70, 70, 2])
        with tf.variable_scope("discriminator", reuse=tf.AUTO_REUSE):
            with tf.variable_scope("conv1"):
                inputs = leaky_relu(conv2d("conv1", inputs, 64, 5, 2))
            with tf.variable_scope("conv2"):
                inputs = leaky_relu(instanceNorm("in1", conv2d("conv2", inputs, 128, 5, 2)))
            with tf.variable_scope("conv3"):
                inputs = leaky_relu(instanceNorm("in2", conv2d("conv3", inputs, 256, 5, 2)))
            with tf.variable_scope("conv4"):
                inputs = leaky_relu(instanceNorm("in3", conv2d("conv4", inputs, 512, 5, 2)))
            with tf.variable_scope("outputs"):
                inputs = conv2d("conv5", inputs, 1, 5, 1)
            return inputs

    def generator(self, inputs_condition):
        inputs = inputs_condition
        with tf.variable_scope("generator"):
            inputs1 = leaky_relu(conv2d("conv1", inputs, 64, 5, 2))#128x128x128
            inputs2 = leaky_relu(instanceNorm("in1", conv2d("conv2", inputs1, 128, 5, 2)))#64x64x256
            inputs3 = leaky_relu(instanceNorm("in2", conv2d("conv3", inputs2, 256, 5, 2)))#32x32x512
            inputs4 = leaky_relu(instanceNorm("in3", conv2d("conv4", inputs3, 512, 5, 2)))#16x16x512
            inputs5 = leaky_relu(instanceNorm("in4", conv2d("conv5", inputs4, 512, 5, 2)))#8x8x512
            inputs6 = leaky_relu(instanceNorm("in5", conv2d("conv6", inputs5, 512, 5, 2)))#4x4x512
            inputs7 = leaky_relu(instanceNorm("in6", conv2d("conv7", inputs6, 512, 5, 2)))#2x2x512
            inputs8 = leaky_relu(instanceNorm("in7", conv2d("conv8", inputs7, 512, 5, 2)))#1x1x512
            outputs1 = tf.nn.relu(tf.concat([tf.nn.dropout(instanceNorm("in9", deconv2d("dconv1", inputs8, 512, 5, 2)), 0.5), inputs7], axis=3))  # 2x2x512
            outputs2 = tf.nn.relu(tf.concat([tf.nn.dropout(instanceNorm("in10", deconv2d("dconv2", outputs1, 512, 5, 2)), 0.5), inputs6], axis=3))  # 4x4x512
            outputs3 = tf.nn.relu(tf.concat([tf.nn.dropout(instanceNorm("in11", deconv2d("dconv3", outputs2, 512, 5, 2)), 0.5), inputs5], axis=3))#8x8x512
            outputs4 = tf.nn.relu(tf.concat([instanceNorm("in12", deconv2d("dconv4", outputs3, 512, 5, 2)), inputs4], axis=3))#16x16x512
            outputs5 = tf.nn.relu(tf.concat([instanceNorm("in13", deconv2d("dconv5", outputs4, 256, 5, 2)), inputs3], axis=3))#32x32x256
            outputs6 = tf.nn.relu(tf.concat([instanceNorm("in14", deconv2d("dconv6", outputs5, 128, 5, 2)), inputs2], axis=3))#64x64x128
            outputs7 = tf.nn.relu(tf.concat([instanceNorm("in15", deconv2d("dconv7", outputs6, 64, 5, 2)), inputs1], axis=3))#128x128x64
            outputs8 = tf.nn.tanh((deconv2d("dconv8", outputs7, 3, 5, 2)))#256x256x3
            return outputs8


if __name__ == "__main__":
    gan = pix2pix()
    pass

# saver = tf.train.Saver(tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, "generator"))
# saver.restore(self.sess, "C://Users//gmt//Desktop//rdb//.\\takeoffnoise_patch_RDB.ckpt")
# self.mean_psnr_ssim()
