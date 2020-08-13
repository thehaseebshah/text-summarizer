import tensorflow.keras as keras

from tensorflow.python.keras.utils import to_categorical
import numpy as np
import os, sys

project_path = os.environ.get("PWD")
if project_path not in sys.path:
    sys.path.append(project_path)

from examples.utils.data_helper import read_data, sents2sequences, get_data
from examples.nmt_bidirectional.model import define_nmt
from examples.utils.model_helper import plot_attention_weights
from examples.utils.logger import get_logger
from examples.utils.config import Config

config = Config()

logger = get_logger("examples.nmt_bidirectional.train", config.LOGS_DIR)

batch_size = 64
hidden_size = 96
en_timesteps, fr_timesteps = 20, 20


def preprocess_data(en_tokenizer, fr_tokenizer, en_text, fr_text, en_timesteps, fr_timesteps):
    """ Preprocessing data and getting a sequence of word indices """

    en_seq = sents2sequences(en_tokenizer, en_text, reverse=False, padding_type='pre', pad_length=en_timesteps)
    fr_seq = sents2sequences(fr_tokenizer, fr_text, pad_length=fr_timesteps)
    logger.info('Vocabulary size (English): {}'.format(np.max(en_seq)+1))
    logger.info('Vocabulary size (French): {}'.format(np.max(fr_seq)+1))
    logger.debug('En text shape: {}'.format(en_seq.shape))
    logger.debug('Fr text shape: {}'.format(fr_seq.shape))

    return en_seq, fr_seq


def train(full_model, en_seq, fr_seq, batch_size, n_epochs=10):
    """ Training the model """

    for ep in range(n_epochs):
        losses = []
        for bi in range(0, en_seq.shape[0] - batch_size, batch_size):

            en_onehot_seq = to_categorical(en_seq[bi:bi + batch_size, :], num_classes=en_vsize)
            fr_onehot_seq = to_categorical(fr_seq[bi:bi + batch_size, :], num_classes=fr_vsize)

            full_model.train_on_batch([en_onehot_seq, fr_onehot_seq[:, :-1, :]], fr_onehot_seq[:, 1:, :])

            l = full_model.evaluate([en_onehot_seq, fr_onehot_seq[:, :-1, :]], fr_onehot_seq[:, 1:, :],
                                    batch_size=batch_size, verbose=0)

            losses.append(l)
        if (ep + 1) % 1 == 0:
            logger.info("Loss in epoch {}: {}".format(ep + 1, np.mean(losses)))


def infer_nmt(encoder_model, decoder_model, test_en_seq, en_vsize, fr_vsize):
    """
    Infer logic
    :param encoder_model: keras.Model
    :param decoder_model: keras.Model
    :param test_en_seq: sequence of word ids
    :param en_vsize: int
    :param fr_vsize: int
    :return:
    """

    test_fr_seq = sents2sequences(fr_tokenizer, ['sos'], fr_vsize)
    test_en_onehot_seq = to_categorical(test_en_seq, num_classes=en_vsize)
    test_fr_onehot_seq = np.expand_dims(to_categorical(test_fr_seq, num_classes=fr_vsize), 1)

    enc_outs, enc_fwd_state, enc_back_state = encoder_model.predict(test_en_onehot_seq)
    dec_state = np.concatenate([enc_fwd_state, enc_back_state], axis=-1)
    attention_weights = []
    fr_text = ''

    for i in range(fr_timesteps):

        dec_out, attention, dec_state = decoder_model.predict(
            [enc_outs, dec_state, test_fr_onehot_seq])
        dec_ind = np.argmax(dec_out, axis=-1)[0, 0]

        if dec_ind == 0:
            break
        test_fr_seq = sents2sequences(fr_tokenizer, [fr_index2word[dec_ind]], fr_vsize)
        test_fr_onehot_seq = np.expand_dims(to_categorical(test_fr_seq, num_classes=fr_vsize), 1)

        attention_weights.append((dec_ind, attention))
        fr_text += fr_index2word[dec_ind] + ' '

    return fr_text, attention_weights


if __name__ == '__main__':
    debug = False

    """ Hyperparameters """

    train_size = 100000 if not debug else 10000
    filename = ''
    tr_en_text, tr_fr_text, ts_en_text, ts_fr_text = get_data(train_size=train_size)

    """ Defining tokenizers """
    en_tokenizer = keras.preprocessing.text.Tokenizer(oov_token='UNK')
    en_tokenizer.fit_on_texts(tr_en_text)

    fr_tokenizer = keras.preprocessing.text.Tokenizer(oov_token='UNK')
    fr_tokenizer.fit_on_texts(tr_fr_text)

    """ Getting preprocessed data """
    en_seq, fr_seq = preprocess_data(en_tokenizer, fr_tokenizer, tr_en_text, tr_fr_text, en_timesteps, fr_timesteps)

    en_vsize = max(en_tokenizer.index_word.keys()) + 1
    fr_vsize = max(fr_tokenizer.index_word.keys()) + 1

    """ Defining the full model """
    full_model, infer_enc_model, infer_dec_model = define_nmt(
        hidden_size=hidden_size, batch_size=batch_size,
        en_timesteps=en_timesteps, fr_timesteps=fr_timesteps,
        en_vsize=en_vsize, fr_vsize=fr_vsize)

    n_epochs = 10 if not debug else 3
    train(full_model, en_seq, fr_seq, batch_size, n_epochs)

    """ Save model """
    if not os.path.exists(config.MODELS_DIR):
        os.mkdir(config.MODELS_DIR)
    full_model.save(os.path.join(config.MODELS_DIR, 'nmt_bidirectional.h5'))

    """ Index2word """
    en_index2word = dict(zip(en_tokenizer.word_index.values(), en_tokenizer.word_index.keys()))
    fr_index2word = dict(zip(fr_tokenizer.word_index.values(), fr_tokenizer.word_index.keys()))

    """ Inferring with trained model """

    np.random.seed(100)
    rand_test_ids = np.random.randint(0, len(ts_en_text), size=10)
    for rid in rand_test_ids:
        test_en = ts_en_text[rid]
        logger.info('\nTranslating: {}'.format(test_en))

        test_en_seq = sents2sequences(en_tokenizer, [test_en], pad_length=en_timesteps)
        test_fr, attn_weights = infer_nmt(
            encoder_model=infer_enc_model, decoder_model=infer_dec_model,
            test_en_seq=test_en_seq, en_vsize=en_vsize, fr_vsize=fr_vsize)
        logger.info('\tFrench: {}'.format(test_fr))

        """ Attention plotting """
        plot_attention_weights(test_en_seq, attn_weights, en_index2word, fr_index2word, filename='attention_{}.png'.format(rid))