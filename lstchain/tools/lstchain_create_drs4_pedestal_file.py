"""
Create drs4 time pedestal fits file.
"""
import numpy as np
from astropy.io import fits

from ctapipe.core import Provenance, traits
from ctapipe.core import Tool
from ctapipe.io import EventSource
from lstchain.calib.camera.r0 import LSTR0Corrections
from lstchain.calib.camera.drs4 import DragonPedestal


class PedestalFITSWriter(Tool):

    name = "PedestalFITSWriter"
    description = "Generate a pedestal FITS file"

    output = traits.Path(
        default_value="pedestal.fits",
        help="Path to the generated fits pedestal file",
        directory_ok=False,
        exists=False,
    ).tag(config=True)

    deltaT = traits.Bool(
        help="Flag to use deltaT correction. Default=True", default_value=True
    ).tag(config=True)

    aliases = {
        "input": "EventSource.input_url",
        "output": "PedestalFITSWriter.output_file"
    }

    flags = {
        "deltaT": ({"PedestalFITSWriter": {"deltaT": True}}, "Flag to use deltaT correction. Default is True")
    }

    classes = [EventSource, LSTR0Corrections, DragonPedestal]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        """
        Tool that generates a pedestal FITS file for low level calibration.

        For getting help run:
        lstchain_create_drs4_pedestal_file --help
        """

        self.eventsource = None
        self.pixel_ids = None
        self.pedestal = None
        self.lst_r0 = None

    def setup(self):

        self.log.debug("Opening file")
        self.eventsource = EventSource.from_config(parent=self)
        self.lst_r0 = self.add_component(LSTR0Corrections(parent=self))

        for event in self.eventsource:
            tel_id = event.r0.tels_with_data[0]
            self.pixel_ids = event.lst.tel[tel_id].svc.pixel_ids
            self.pedestal = DragonPedestal(tel_id=tel_id, n_module=event.lst.tel[tel_id].svc.num_modules)
            break

    def start(self):

        try:
            if self.deltaT:
                self.log.info("DeltaT correction active")
                for i, event in enumerate(self.eventsource):
                    for tel_id in event.r0.tels_with_data:
                        self.lst_r0.time_lapse_corr(event, tel_id)
                        self.pedestal.fill_pedestal_event(event)
                        if i % 500 == 0:
                            self.log.debug(f"i = {i}, ev id = {event.index.event_id}")
            else:
                self.log.info("DeltaT correction no active")
                for i, event in enumerate(self.eventsource):
                    self.pedestal.fill_pedestal_event(event)
                    if i % 500 == 0:
                        self.log.debug(f"i = {i}, ev id = {event.index.event_id}")

            self.pedestal.finalize_pedestal()

        except Exception as e:
            self.log.error(e)

    def finish(self):

        primaryhdu = fits.PrimaryHDU(self.pixel_ids)
        secondhdu = fits.ImageHDU(np.int16(self.pedestal.meanped))
        hdulist = fits.HDUList([primaryhdu, secondhdu])
        hdulist.writeto(self.output)

        Provenance().add_output_file(
            self.output,
            role='mon.tel.pedestal'
        )


def main():
    exe = PedestalFITSWriter()
    exe.run()


if __name__ == "__main__":
    main()
