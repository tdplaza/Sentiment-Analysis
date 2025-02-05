import numpy as np
import pandas as pd
from keras import backend as K
from keras import initializers, regularizers, constraints
from keras.callbacks import EarlyStopping, ModelCheckpoint
from keras.engine.topology import Layer
from keras.layers import Dense, Embedding, Input
from keras.layers import LSTM, Bidirectional, Dropout
from keras.models import Model
from keras.preprocessing import text, sequence

np.random.seed(7)


class Attention(Layer):
    def __init__(self, step_dim,
                 W_regularizer=None, b_regularizer=None,
                 W_constraint=None, b_constraint=None,
                 bias=True, **kwargs):
        self.supports_masking = True
        self.init = initializers.get('glorot_uniform')

        self.W_regularizer = regularizers.get(W_regularizer)
        self.b_regularizer = regularizers.get(b_regularizer)

        self.W_constraint = constraints.get(W_constraint)
        self.b_constraint = constraints.get(b_constraint)

        self.bias = bias
        self.step_dim = step_dim
        self.features_dim = 0
        super(Attention, self).__init__(**kwargs)

    def build(self, input_shape):
        assert len(input_shape) == 3

        self.W = self.add_weight(shape=(input_shape[-1],),
                                 initializer=self.init,
                                 name='{}_W'.format(self.name),
                                 regularizer=self.W_regularizer,
                                 constraint=self.W_constraint)
        self.features_dim = input_shape[-1]

        if self.bias:
            self.b = self.add_weight(shape=(input_shape[1],),
                                     initializer='zero',
                                     name='{}_b'.format(self.name),
                                     regularizer=self.b_regularizer,
                                     constraint=self.b_constraint)
        else:
            self.b = None

        self.built = True

    def compute_mask(self, input, input_mask=None):
        return None

    def call(self, x, mask=None):
        features_dim = self.features_dim
        step_dim = self.step_dim

        eij = K.reshape(K.dot(K.reshape(x, (-1, features_dim)),
                        K.reshape(self.W, (features_dim, 1))), (-1, step_dim))

        if self.bias:
            eij += self.b

        eij = K.tanh(eij)

        a = K.exp(eij)

        if mask is not None:
            a *= K.cast(mask, K.floatx())

        a /= K.cast(K.sum(a, axis=1, keepdims=True) + K.epsilon(), K.floatx())

        a = K.expand_dims(a)
        weighted_input = x * a
        return K.sum(weighted_input, axis=1)

    def compute_output_shape(self, input_shape):
        return input_shape[0],  self.features_dim



def BidLstm(maxlen, max_features, embed_size, embedding_matrix):
    inp = Input(shape=(maxlen, ))
    embedding_output = Embedding(max_features, embed_size, weights=[embedding_matrix],trainable=False)(inp)
    lstm_output = Bidirectional(LSTM(300, return_sequences=True, dropout=0.25,recurrent_dropout=0.25))(embedding_output)
    attention_output = Attention(maxlen)(lstm_output)
    dense_output_1 = Dense(256, activation="relu")(attention_output)
    dropout_output = Dropout(0.25)(dense_output_1)
    dense_output_2 = Dense(6, activation="sigmoid")(dropout_output)
    model_ = Model(inputs=inp, outputs=dense_output_2)
    print(model_.output_shape)
    return model_



def make_df(train_path, test_path, max_features, maxlen, list_classes):
    train = pd.read_csv(train_path)
    test = pd.read_csv(test_path)
    train = train.sample(frac=1)

    list_sentences_train = train["comment_text"].fillna("unknown").values
    y = train[list_classes].values
    list_sentences_test = test["comment_text"].fillna("unknown").values

    tokenizer = text.Tokenizer(num_words=max_features)
    tokenizer.fit_on_texts(list(list_sentences_train))
    list_tokenized_train = tokenizer.texts_to_sequences(list_sentences_train)
    list_tokenized_test = tokenizer.texts_to_sequences(list_sentences_test)
    X_t = sequence.pad_sequences(list_tokenized_train, maxlen=maxlen)
    X_te = sequence.pad_sequences(list_tokenized_test, maxlen=maxlen)
    word_index = tokenizer.word_index

    return X_t, X_te, y, word_index






def make_glovevec(glovepath, max_features, embed_size, word_index, veclen=300):
    embeddings_index = {}
    f = open(glovepath, encoding='utf-8')
    for line in f:
        values = line.split()
        word = ' '.join(values[:-300])
        coefs = np.asarray(values[-300:], dtype='float32')
        embeddings_index[word] = coefs.reshape(-1)
    f.close()

    nb_words = min(max_features, len(word_index))
    embedding_matrix = np.zeros((nb_words, embed_size))
    for word, i in word_index.items():
        if i >= max_features:
            continue
        embedding_vector = embeddings_index.get(word)
        if embedding_vector is not None:
            embedding_matrix[i] = embedding_vector
    return embedding_matrix




if __name__ == "__main__":
    max_features = 100000
    maxlen = 150
    embed_size = 300
    list_classes = ["toxic", "severe_toxic", "obscene", "threat", "insult","identity_hate"]

    xtr, xte, y, word_index = make_df( train_path= "data/processed/train.csv", test_path="data/processed/test.csv", max_features=max_features, maxlen=maxlen, list_classes=list_classes)

    embedding_vector = make_glovevec("data/glove.840B.300d.txt",max_features, embed_size, word_index)

    model = BidLstm(maxlen, max_features, embed_size, embedding_matrix=embedding_vector)
    model.compile(loss='binary_crossentropy', optimizer='adam',metrics=['accuracy'])
    file_path = ".model.hdf5"
    ckpt = ModelCheckpoint(file_path, monitor='val_loss', verbose=1,
                           save_best_only=True, mode='min')
    early = EarlyStopping(monitor="val_loss", mode="min", patience=1)
    #model.fit(xtr, y, batch_size=256, epochs=15, validation_split=0.1, callbacks=[ckpt, early])
    model.fit(xtr, y, batch_size=256, epochs=1, validation_split=0.1)

    model.load_weights(file_path)
    y_test = model.predict(xte)
    sample_submission = pd.read_csv("data/processed/sample_submission.csv")
    sample_submission[list_classes] = y_test
    sample_submission.to_csv("sub.csv", index=False)