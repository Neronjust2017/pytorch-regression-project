import numpy as np
import torch
from torch.utils.data import DataLoader
from torch.utils.data.dataloader import default_collate
from torch.utils.data.sampler import SubsetRandomSampler
from torch.utils.data.dataset import Subset

from torch.utils.data import TensorDataset


class BaseDataLoader(DataLoader):
    """
    Base class for all data loaders
    """
    def __init__(self, dataset, batch_size, shuffle, validation_split, test_split, num_workers, collate_fn=default_collate,  normalization=False):
        self.validation_split = validation_split
        self.test_split = test_split
        self.shuffle = shuffle
        self.dataset =dataset
        self.batch_idx = 0
        self.n_samples = len(self.dataset)

        self.sampler, self.valid_sampler, self.test_subset = self._split_sampler(self.validation_split, self.test_split, normalization)

        self.init_kwargs = {
            'dataset': self.dataset,
            'batch_size': batch_size,
            'shuffle': self.shuffle,
            'collate_fn': collate_fn,
            'num_workers': num_workers
        }
        super().__init__(sampler=self.sampler, **self.init_kwargs)

        self.valid_data_loader = self.split_validation()

        self.test_data_loader_init_kwargs = {
            'batch_size': batch_size,
            'shuffle': False,
            'collate_fn': collate_fn,
            'num_workers': num_workers
        }

        self.test_data_loader = self.split_test()

    def _split_sampler(self, validation_split, test_split, normalization):
        if validation_split == 0.0 and test_split == 0.0:
            return None, None, None

        idx_full = np.arange(self.n_samples)

        np.random.seed(1)
        np.random.shuffle(idx_full)

        if isinstance(validation_split, int):
            assert validation_split > 0
            assert validation_split < self.n_samples, "validation set size is configured to be larger than entire dataset."
            len_valid = validation_split
        else:
            len_valid = int(self.n_samples * validation_split)

        if isinstance(test_split, int):
            assert test_split > 0
            assert test_split < self.n_samples, "validation set size is configured to be larger than entire dataset."
            len_test = test_split
        else:
            len_test = int(self.n_samples * test_split)

        valid_idx = idx_full[0:len_valid]
        test_idx = idx_full[len_valid:len_valid+len_test]
        train_idx = np.delete(idx_full, np.arange(0, len_valid + len_test))

        if normalization:
            self.data_normalization(train_idx, valid_idx, test_idx)

        train_sampler = SubsetRandomSampler(train_idx)
        valid_sampler = SubsetRandomSampler(valid_idx)
        # test_sampler = SubsetRandomSampler(test_idx)
        test_subset = Subset(self.dataset, test_idx)

        # turn off shuffle option which is mutually exclusive with sampler
        self.shuffle = False
        self.n_samples = len(train_idx)
        self.valid_n_samples = len(valid_idx)
        self.test_n_samples = len(test_idx)

        return train_sampler, valid_sampler, test_subset

    def split_validation(self):
        if self.valid_sampler is None:
            return None
        else:
            valid_data_loader = DataLoader(sampler=self.valid_sampler, **self.init_kwargs)
            valid_data_loader.n_samples = self.valid_n_samples
            return valid_data_loader

    def split_test(self):
        if self.split_test is None:
            return None
        else:
            test_data_loader = DataLoader(self.test_subset, **self.test_data_loader_init_kwargs)
            test_data_loader.n_samples = self.test_n_samples
            return test_data_loader

    def data_normalization(self, train_idx, val_idx, test_idx):

        X = self.dataset[:][0]
        Y = self.dataset[:][1]

        X_train = X[train_idx]
        y_train = Y[train_idx]
        X_val = X[val_idx]
        y_val = Y[val_idx]
        X_test = X[test_idx]
        y_test = Y[test_idx]

        x_means, x_stds = X_train.mean(axis=0), X_train.var(axis=0) ** 0.5
        y_means, y_stds = y_train.mean(axis=0), y_train.var(axis=0) ** 0.5
        
        X_normal = torch.zeros(*X.shape)
        Y_normal = torch.zeros(*Y.shape)
        
        X_normal[train_idx] = (X_train - x_means) / x_stds
        Y_normal[train_idx] = (y_train - y_means) / y_stds

        X_normal[val_idx] = (X_val - x_means) / x_stds
        Y_normal[val_idx] = (y_val - y_means) / y_stds

        X_normal[test_idx] = (X_test - x_means) / x_stds
        Y_normal[test_idx] = (y_test - y_means) / y_stds

        self.dataset = TensorDataset(X_normal, Y_normal)


class BaseDataLoader_2(DataLoader):
    """
    Base class for all data loaders
    """

    def __init__(self, dataset, batch_size, shuffle, train_idx, valid_idx, test_idx, num_workers,
                 collate_fn=default_collate, normalization=False):
        self.train_idx = train_idx
        self.valid_idx = valid_idx
        self.test_idx = test_idx
        self.shuffle = shuffle
        self.dataset = dataset
        self.batch_idx = 0
        self.n_samples = len(self.dataset)

        self.sampler, self.valid_sampler, self.test_sampler = self._split_sampler(self.train_idx, self.valid_idx,
                                                                                  self.test_idx, normalization)

        self.init_kwargs = {
            'dataset': self.dataset,
            'batch_size': batch_size,
            'shuffle': self.shuffle,
            'collate_fn': collate_fn,
            'num_workers': num_workers
        }
        super().__init__(sampler=self.sampler, **self.init_kwargs)

        self.valid_data_loader = self.split_validation()
        self.test_data_loader = self.split_test()

    def _split_sampler(self, train_idx, valid_idx, test_idx, normalization):
        if valid_idx is None and test_idx is None:
            return None, None, None
        if normalization:
            self.data_normalization(train_idx, valid_idx, test_idx)

        train_sampler = SubsetRandomSampler(train_idx)
        valid_sampler = SubsetRandomSampler(valid_idx)
        test_sampler = SubsetRandomSampler(test_idx)

        # turn off shuffle option which is mutually exclusive with sampler
        self.shuffle = False
        self.n_samples = len(train_idx)
        self.valid_n_samples = len(valid_idx)
        self.test_n_samples = len(test_idx)

        return train_sampler, valid_sampler, test_sampler

    def split_validation(self):
        if self.valid_idx is None:
            return None
        else:
            valid_data_loader = DataLoader(sampler=self.valid_sampler, **self.init_kwargs)
            valid_data_loader.n_samples = self.valid_n_samples
            return valid_data_loader

    def split_test(self):
        if self.test_idx is None:
            return None
        else:
            test_data_loader = DataLoader(sampler=self.test_sampler, **self.init_kwargs)
            test_data_loader.n_samples = self.test_n_samples
            return test_data_loader

    def data_normalization(self, train_idx, val_idx, test_idx):

        X = self.dataset[:][0]
        Y = self.dataset[:][1]

        X_train = X[train_idx]
        y_train = Y[train_idx]
        X_val = X[val_idx]
        y_val = Y[val_idx]
        X_test = X[test_idx]
        y_test = Y[test_idx]

        x_means, x_stds = X_train.mean(axis=0), X_train.var(axis=0) ** 0.5
        y_means, y_stds = y_train.mean(axis=0), y_train.var(axis=0) ** 0.5

        X_normal = torch.zeros(*X.shape)
        Y_normal = torch.zeros(*Y.shape)

        X_normal[train_idx] = (X_train - x_means) / x_stds
        Y_normal[train_idx] = (y_train - y_means) / y_stds

        X_normal[val_idx] = (X_val - x_means) / x_stds
        Y_normal[val_idx] = (y_val - y_means) / y_stds

        X_normal[test_idx] = (X_test - x_means) / x_stds
        Y_normal[test_idx] = (y_test - y_means) / y_stds

        self.dataset = TensorDataset(X_normal, Y_normal)