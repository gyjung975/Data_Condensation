import argparse
import os
import time

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torchvision import datasets, transforms
import torch.optim as optim
import torchvision.models as models
from torchvision.utils import save_image


# class Generator(nn.Module):
#     def __init__(self, args):
#         super(Generator, self).__init__()
#         self.args = args
#
#         def block(in_dim, out_dim, normalize=True):
#             layers = [nn.Linear(in_dim, out_dim)]
#             if normalize:
#                 layers.append(nn.BatchNorm1d(out_dim, 0.8))
#             layers.append(nn.LeakyReLU(0.2, inplace=True))
#             return layers
#
#         self.model = nn.Sequential(
#             *block(args.latent_dim, 128, normalize=False),
#             *block(128, 256),
#             *block(256, 512),
#             *block(512, 1024),
#             nn.Linear(1024, int(np.prod(img_shape))),
#             nn.Tanh())
#
#     def forward(self, z):
#         img = self.model(z)
#         img = img.view(img.size(0), *img_shape)
#         return img


class Generator(nn.Module):
    def __init__(self, args):
        super(Generator, self).__init__()
        self.args = args
        self.init_size = img_shape[1] // 4
        self.l1 = nn.Sequential(
            nn.Linear(args.latent_dim, 128 * self.init_size ** 2))

        self.conv_blocks = nn.Sequential(
            nn.BatchNorm2d(128),
            nn.Upsample(scale_factor=2),
            nn.Conv2d(128, 128, 3, stride=1, padding=1),
            nn.BatchNorm2d(128, 0.8),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Upsample(scale_factor=2),
            nn.Conv2d(128, 64, 3, stride=1, padding=1),
            nn.BatchNorm2d(64, 0.8),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(64, img_shape[0], 3, stride=1, padding=1),
            nn.Tanh(),
        )

    def forward(self, z):
        out = self.l1(z)
        out = out.view(out.shape[0], 128, self.init_size, self.init_size)
        img = self.conv_blocks(out)
        return img


class Discriminator(nn.Module):
    def __init__(self, args):
        super(Discriminator, self).__init__()
        self.args = args

        self.model = nn.Sequential(nn.Linear(int(np.prod(img_shape)), 512),
                                   nn.LeakyReLU(0.2, inplace=True),
                                   nn.Linear(512, 256),
                                   nn.LeakyReLU(0.2, inplace=True),
                                   nn.Linear(256, 1),
                                   nn.Sigmoid())

    def forward(self, img):
        flattened = img.view(img.size(0), -1)
        output = self.model(flattened)
        return output


def _init_():
    if not os.path.exists('outputs'):
        os.makedirs('outputs')
    if not os.path.exists('outputs/' + args.exp_name):
        os.makedirs('outputs/' + args.exp_name)


start_time = time.time()


def train(args):
    transform_train = transforms.Compose([transforms.ToTensor(),
                                          transforms.Normalize([0.5], [0.5])])
    if args.dataset == 'MNIST':
        train_dataset = datasets.MNIST(root='./data', train=True, transform=transform_train)
    else:
        train_dataset = datasets.CIFAR10(root='./data/CIFAR10', train=True, transform=transform_train)

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)

    device = torch.device('cuda')
    generator = Generator(args).to(device)
    discriminator = Discriminator(args).to(device)

    criterion = nn.BCELoss().to(device)
    optimizer_G = optim.Adam(generator.parameters(), lr=args.lr, betas=(0.5, 0.999))
    optimizer_D = optim.Adam(discriminator.parameters(), lr=args.lr, betas=(0.5, 0.999))

    best_acc = 0
    for epoch in range(args.epochs):
        generator.train()
        discriminator.train()
        g_loss = 0
        d_loss = 0
        count = 0

        for i, (imgs, _) in enumerate(train_loader):
            real_imgs = imgs.to(device)

            with torch.no_grad():
                real_label = torch.FloatTensor(imgs.size(0), 1).fill_(1.0).to(device)
                fake_label = torch.FloatTensor(imgs.size(0), 1).fill_(0.0).to(device)

            z = torch.FloatTensor(np.random.normal(0, 1, (imgs.shape[0], args.latent_dim))).to(device)
            # z = torch.normal(mean=0, std=1, size=(imgs.shape[0], args.latent_dim)).to(device)

            optimizer_G.zero_grad()
            gen_imgs = generator(z)
            g_loss = criterion(discriminator(gen_imgs), real_label)
            g_loss.backward()
            optimizer_G.step()

            optimizer_D.zero_grad()
            real_loss = criterion(discriminator(real_imgs), real_label)
            fake_loss = criterion(discriminator(gen_imgs.detach()), fake_label)
            d_loss = (real_loss + fake_loss) / 2
            d_loss.backward()
            optimizer_D.step()

            g_loss += g_loss.item() * args.batch_size
            d_loss += d_loss.item() * args.batch_size
            count += (discriminator(gen_imgs) >= 0.5).sum()

            done = epoch * len(train_loader) + i
            if done % args.sample_interval == 0:
                save_image(gen_imgs.data[:25], "outputs/%s/%d.png" % (args.exp_name,
                                                                      done / args.sample_interval),
                           nrow=5, normalize=True)
        g_loss /= len(train_loader.dataset)
        d_loss /= len(train_loader.dataset)
        gen_acc = 100 * count / len(train_loader.dataset)
        print("[Epoch %d/%d] [D loss: %f] [G loss: %f] [G axx: %.2f] [time: %f]" % (epoch + 1,
                                                                                    args.epochs,
                                                                                    d_loss.item(),
                                                                                    g_loss.item(),
                                                                                    gen_acc,
                                                                                    time.time() - start_time))
        # if gen_acc >= best_acc:
        #     best_acc = gen_acc
        #     torch.save(generator.state_dict(), 'outputs/%s/gen_model.t7' % (args.exp_name))
        #     torch.save(discriminator.state_dict(), 'outputs/%s/dis_model.t7' % (args.exp_name))


def test(args):
    device = torch.device('cuda')

    generator = Generator(args).to(device)
    generator.load_state_dict(torch.load(os.path.join(args.model_path, 'gen_model.t7')))

    discriminator = Discriminator(args).to(device)
    discriminator.load_state_dict(torch.load(os.path.join(args.model_path, 'dis_model.t7')))

    generator.eval()
    discriminator.eval()

    z = torch.FloatTensor(np.random.normal(0, 1, (args.num_imgs, args.latent_dim))).to(device)
    # z = torch.normal(mean=0, std=1, size=(args.num_imgs, args.latent_dim)).to(device)

    gen_imgs = generator(z)

    fake = (discriminator(gen_imgs.detach()) >= 0.5).sum()
    fake_acc = 100 * fake / args.num_img

    save_image(gen_imgs, "%s/%s.png" % (args.model_path, args.exp_name), nrow=5, normalize=True)
    print(discriminator(gen_imgs.detach()) >= 0.5)
    print("Fake acc: %.2f" % fake_acc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--exp_name', type=str, default='gan')
    parser.add_argument('--epochs', type=int, default=200)
    parser.add_argument('--batch_size', type=int, default=128)
    parser.add_argument('--lr', type=float, default=0.0002)
    parser.add_argument('--latent_dim', type=int, default=100)
    parser.add_argument('--dataset', type=str, default='MNIST',
                        choices=['MNIST', 'CIFAR10'])
    parser.add_argument('--sample_interval', type=int, default=2000)
    parser.add_argument('--num_img', type=int, default=10)
    parser.add_argument('--eval', type=bool, default=False)
    parser.add_argument('--model_path', type=str, default='')   # outputs/exp_name
    args = parser.parse_args()
    print(args)

    _init_()

    if args.dataset == 'MNIST':
        img_shape = (1, 28, 28)
    else:
        img_shape = (3, 32, 32)

    if not args.eval:
        train(args)
    else:
        test(args)
