#!/usr/bin/env python3

"""
Tests a batch of transferred models on all class types.  Calculates and outputs
the recall for each class to a CSV file.

The parameter `models_dir` should point to a directory that resembles the
following:

    models_dir
    ├── mesoinception4
    │   ├── df-to-f2f
    │   │   └── best.hdf5
    │   ├── df-to-fs
    │   │   └── best.hdf5
    │   ├── df-to-gann
    │   │   └── best.hdf5
    │   ├── df-to-icf
    │   │   └── best.hdf5
    │   ├── df-to-x2f
    │   │   └── best.hdf5
    │   ├── f2f-to-df
    │   │   └── best.hdf5
    │   ├── f2f-to-fs
    │   │   └── best.hdf5
    │   └── ...
    └── ...

The headers of the CSV file are:

    mtype, orig_class, trans_class, real, df, f2f, fs, gann, icf, x2f

where "mtype" stand for "model type", "orig_class" for "original class",
"trans_class" for "transfer class" (the class the model was transferred to),
"df" for "Deepfakes", "f2f" for "Face2Face", "fs" for "FaceSwap", "icf" for
"ICface", and "x2f" for "X2Face". The value in each class-labeled column is the
recall for the transferred model for that class.
"""

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Silence Tensorflow warnings.

import argparse
import csv
from keras.backend.tensorflow_backend import set_session
from keras.preprocessing.image import ImageDataGenerator
import numpy as np
import tensorflow as tf
from tensorflow.keras.callbacks import Callback
from sys import stderr

from classifiers import CLASS_MODES, MODEL_MAP
from utils import load_single_class_generators

# Silence Tensorflow warnings.
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)

def main(data_dir, models_dir, mtype, output_file, batch_size=16):
    """
    Tests transferred models on every class type.

    Args:
        data_dir: Directory containing directories with test images for all
            classes.
        models_dir: Models directory as described in this script's docstring.
        mtype: Architecture of models to test.
        output_file: CSV file to output to.
        batch_size: Number of images to process at a time.
    """
    # Make sure model is valid.
    if not mtype in MODEL_MAP:
        print('ERROR: "{}" is not a valid model type'.format(mtype),
              file=stderr)
        exit(2)

    print('Testing transferred models for {}'.format(mtype.upper()))
    print('Loading models from "{}"'.format(models_dir))
    print('Outputting to "{}"'.format(output_file))
    print('Batch size: {}'.format(batch_size))

    # Open output file.  Initialize with headers if it does not exist.
    init_output = not os.path.exists(output_file)
    output = open(output_file, 'a')
    output_csv = csv.writer(output)
    if init_output:
        headers = ('mtype', 'orig_class', 'trans_class',
                   'real', 'df', 'f2f', 'fs', 'gann', 'icf', 'x2f')
        output_csv.writerow(headers)

    classes = ('real', 'df', 'f2f', 'fs', 'gann', 'icf', 'x2f')

    # Maps a class' name to a data generator.
    print('\nLoading generators...')
    generators = load_single_class_generators(
        data_dir, classes, batch_size=batch_size)

    mtype_dir = os.path.join(models_dir, mtype.lower())
    if not os.path.isdir(mtype_dir):
        print('ERROR: No directory found for model type "{}" in "{}"'.format(mtype, models_dir),
              file=stderr)
        exit(1)

    # Calculate recall for all models.
    for model_name in sorted(os.listdir(mtype_dir)):
        weights_dir = os.path.join(mtype_dir, model_name)

        # Ignore files.
        if not os.path.isdir(weights_dir):
            continue

        # Make sure best weight parameters are present.
        best_path = os.path.join(weights_dir, 'best.hdf5')
        if not os.path.isfile(best_path):
            print('ERROR: File "{}" does not exist. Skipping.'.format(best_path),
                  file=stderr)
            continue

        print('\nTesting model "{}"...'.format(model_name))

        # Load model.
        model = MODEL_MAP[mtype]()
        model.load(best_path)
        model.set_metrics(['acc'])

        # Calculate recall against each class.
        recalls = {}
        for c in generators:
            gen = generators[c]
            gen.reset()

            # Test model on every compression level.
            _, recalls[c] = model.evaluate_with_generator(gen)

        # Write data.
        orig_class, _, trans_class = model_name.split('-')
        data_line = (mtype.lower(), orig_class, trans_class,
                     recalls['real'], recalls['df'], recalls['f2f'], recalls['fs'],
                     recalls['gann'], recalls['icf'], recalls['x2f'])
        output_csv.writerow(data_line)
        output.flush()

    output.close()

if __name__ == '__main__':
    try:
        desc = 'Tests a batch of transferred models on all class types'
        parser = argparse.ArgumentParser(description=desc)
        parser.add_argument('-d', '--data-dir', dest='data_dir', type=str,
                            required=True, nargs=1,
                            help='Directory containing subdirectories for each class')
        parser.add_argument('-md', '--models_dir', type=str, required=True, nargs=1,
                            default=[None],
                            help='directory described in script description')
        parser.add_argument('-m', '--mtype', type=str, required=True, nargs=1,
                            help='model type')
        parser.add_argument('-o', '--output', dest='output_file', type=str,
                            required=True, nargs=1,
                            help='path to CSV to write or append data to')
        parser.add_argument('-b', '--batch-size', metavar='batch_size', type=int,
                            required=False, nargs=1, default=[16],
                            help='number of images to read at a time')
        parser.add_argument('-g', '--gpu-fraction', metavar='gpu_fraction', type=float,
                            required=False, nargs=1, default=[1.0],
                            help='maximum fraction of the GPU\'s memory the ' \
                            'model is allowed to use, between 0.0 and 1.0')
        args = parser.parse_args()

        data_dir = args.data_dir[0]
        models_dir = args.models_dir[0]
        mtype = args.mtype[0]
        output_file = args.output_file[0]
        batch_size = args.batch_size[0]
        gpu_frac = args.gpu_fraction[0]

        # Validate arguments.
        if not os.path.isdir(data_dir):
            print('"{}" is not a directory'.format(data_dir), file=stderr)
            exit(2)
        if not os.path.isdir(models_dir):
            print('"{}" is not a directory'.format(models_dir), file=stderr)
            exit(2)
        if gpu_frac < 0 or gpu_frac > 1:
            print('gpu-fraction must be between 0.0 and 1.0', file=stderr)
            exit(2)

        config = tf.ConfigProto()
        config.gpu_options.allow_growth = True
        config.gpu_options.per_process_gpu_memory_fraction = gpu_frac
        sess = tf.Session(config=config)
        set_session(sess)

        main(data_dir, models_dir, mtype, output_file, batch_size=batch_size)

    except KeyboardInterrupt:
        print('Program terminated prematurely')
