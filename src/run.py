import logging
import datetime
# import dateutil.parser
import time
import discord

from ebaysdk.exception import ConnectionError
from ebaysdk.finding import Connection

import os
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, filename='../debug.log')

__author__ = "Adam Don"
__version__ = "1.0"


# region Main ----------------------------------------------------------------------------------------------------------


class EbayItem:
    id = None
    name = None
    description = None
    start_time = None
    end_time = None
    listing_type = None
    price = None
    image = None
    url = None

    def __init__(self, id, name, description, start_time, end_time, listing_type, price, image, url):
        self.id = id
        self.name = name
        self.description = description
        self.start_time = start_time
        self.end_time = end_time
        self.listing_type = listing_type
        self.price = price
        self.image = image
        self.url = url

    def is_recent(self, wanted_item: 'WantedItem'):
        then = self.start_time
        now = datetime.datetime.now()
        diff = now - then
        duration_seconds = diff.total_seconds()
        minutes = divmod(duration_seconds, 60)[0]

        if minutes < wanted_item.BIN_RECENT_SINCE_MINS:
            return True
        else:
            return False

    def is_ending_soon(self, wanted_item: 'WantedItem'):
        then = self.end_time
        now = datetime.datetime.now()
        diff = then - now
        duration_seconds = diff.total_seconds()
        minutes = divmod(duration_seconds, 60)[0]

        if minutes < wanted_item.AUCTION_ENDING_MINS:
            return True
        else:
            return False

    def filter(self, wanted_item: 'WantedItem'):
        for anti in wanted_item.anti_keywords:
            if anti in self.name:
                return False
            if anti in self.description:
                return False

        return True

    def send_alert(self):
        # Create webhook
        webhook = discord.Webhook.partial(os.getenv("DISCORD_WEBHOOK_ID"),
                                          os.getenv("DISCORD_WEBHOOK_TOKEN"),
                                          adapter=discord.RequestsWebhookAdapter())

        date_time_str = datetime.datetime.now()
        if type(date_time_str) == str:
            date_time_obj = datetime.strptime(date_time_str, "%Y-%m-%dT%H:%M:%S.%f%z")
        else:
            date_time_obj = date_time_str

        # Build the embed
        embed = discord.Embed(title=self.name, description=self.description, color=0x00ff00)
        # embed.add_field(name='Description', value=self.description, inline=True)
        embed.add_field(name='Price', value='£' + self.price, inline=True)
        embed.add_field(name='Type', value=self.listing_type, inline=True)
        embed.add_field(name=":date: Time of Alert", value=date_time_obj.strftime("%d/%m/%Y  %H:%M %Z"), inline=True)
        embed.add_field(name=':date: Start Time', value=self.start_time.strftime("%d/%m/%Y  %H:%M %Z"), inline=True)
        embed.add_field(name=':date: End Time', value=self.end_time.strftime("%d/%m/%Y  %H:%M %Z"), inline=True)
        embed.add_field(name='URL', value=self.url, inline=True)
        embed.set_image(url=self.image)

        # Send it
        webhook.send(embed=embed)


class WantedItem:
    keywords = None
    anti_keywords = None
    min_price = None
    max_price = None
    condition = None
    api = None
    found_items = {}

    BIN_RECENT_SINCE_MINS = 5000
    AUCTION_ENDING_MINS = 15

    def __init__(self, keywords, min_price, max_price, anti_keywords=[],
                 condition=None):
        self.keywords = keywords
        self.min_price = min_price
        self.max_price = max_price
        self.anti_keywords = anti_keywords
        self.condition = condition

    def connect(self):
        self.api = Connection(appid=os.getenv("EBAY_API_ID"), siteid='EBAY-GB', config_file=None)

    def search_buy_it_now(self):
        api_request = {
            'keywords': self.keywords,
            'itemFilter': [
                {'name': 'FeedbackScoreMin',
                 'value': settings['min_feedback']},
                {'name': 'MaxPrice',
                 'value': self.max_price},
                {'name': 'MinPrice',
                 'value': self.min_price},
                {'name': 'LocatedIn',
                 'value': settings['located_in']},
                {'name': 'ListingType',
                 'value': 'FixedPrice'},
            ],
            'sortOrder': 'StartTimeNewest',
            'descriptionSearch': True,
            'outputSelector': 'AspectHistogram',
        }

        if self.condition is not None:
            api_request['itemFilter'].append({'name': 'Condition',
                                              'value': self.condition})

        # Search for listings
        response = self.api.execute('findItemsAdvanced', api_request)
        response = response.dict()

        # Return results
        items = response['searchResult']['item']
        return items

    def search_auctions(self):
        api_request = {
            'keywords': self.keywords,
            'itemFilter': [
                {'name': 'FeedbackScoreMin',
                 'value': settings['min_feedback']},
                {'name': 'MaxPrice',
                 'value': self.max_price},
                {'name': 'MinPrice',
                 'value': self.min_price},
                {'name': 'LocatedIn',
                 'value': settings['located_in']}
            ],
            'sortOrder': 'EndTimeSoonest',
            'outputSelector': 'AspectHistogram',
            'descriptionSearch': True
        }

        if self.condition is not None:
            api_request['itemFilter'].append({'name': 'Condition',
                                              'value': self.condition})

        # Search for listings
        response = self.api.execute('findItemsAdvanced', api_request)
        response = response.dict()

        # Return results
        items = response['searchResult']['item']
        return items


def main(wanted_items, settings):
    """ Main execution of the app """
    while True:
        try:
            logging.info("{}  :  Looping again...".format(datetime.datetime.now()))

            starttime = time.time()

            for wanted_item in wanted_items:
                wanted_item: WantedItem

                # Connect to API
                wanted_item.connect()

                # Search for latest buy it now / fixed price deals
                buy_it_now_items = wanted_item.search_buy_it_now()
                for item in buy_it_now_items:
                    # Prepare Item
                    time_started = datetime.datetime.strptime(item['listingInfo']['startTime'], '%Y-%m-%dT%H:%M:%S.%fZ')
                    time_ending = datetime.datetime.strptime(item['listingInfo']['endTime'], '%Y-%m-%dT%H:%M:%S.%fZ')

                    ebay_item = EbayItem(item['itemId'], item['title'], '', time_started,
                                         time_ending, item['listingInfo']['listingType'],
                                         item['sellingStatus']['currentPrice']['value'], item['galleryURL'],
                                         item['viewItemURL'])

                    # Check if we have already found and send this.
                    if ebay_item.id not in wanted_item.found_items:

                        # Add to list of found items.
                        wanted_item.found_items[ebay_item.id] = ebay_item

                        # Check if it was recent
                        recent = ebay_item.is_recent(wanted_item)
                        if recent:

                            # Check against our anti keywords to filter out junk
                            filtered = ebay_item.filter(wanted_item)
                            if filtered:
                                # Send alert to discord.
                                ebay_item.send_alert()

                logging.info("{}  :  Ending Loop... ".format(datetime.datetime.now()))

                # Loop every 10 seconds
                time.sleep(20.0 - ((time.time() - starttime) % 20.0))

        except Exception as e:
            # send_exception_email(e)
            logging.error("{}  :  Exception in main: {}".format(datetime.datetime.now(), e))
            print(e)


if __name__ == "__main__":
    """ This is executed when run from the command line. Fill list with wanted items. """
    logging.info("{}  :  Starting...".format(datetime.datetime.now()))

    # Wanted Items
    surface_pro = WantedItem(keywords='Surface Pro 16GB',
                             min_price=100,
                             max_price=1000,
                             anti_keywords=['Surface Pro 4', 'Surface Pro 3', 'like surface pro'])
    wanted_items = [surface_pro]

    # Overall Settings
    settings = {'min_feedback': 5,
                'located_in': 'GB'}

    main(wanted_items, settings)

# endregion ------------------------------------------------------------------------------------------------------------
