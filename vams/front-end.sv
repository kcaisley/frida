`ifndef RD53B_AFE_DIFF_REALMODEL__SV   // include guard
`define RD53B_AFE_DIFF_REALMODEL__SV

//
// Dependencies:
//
// n/a
// Changelog: 4 Feb.2022 (F.Loddo): Remove timewalk and jitter from calibration to make same behavior between BUMP and Injection.
// Changelog: 4 Feb.2022 (F.Loddo): Remove csaRiseRiseTime for HitDelay calculation to make same behavior between BUMP and Injection.
//                                  Also removed charge correction in case of Injection
// Changelog: 7 Feb.2022 (F.Loddo): HitDelay = 1/2 Cycle (12.5 ns). It was 1 Cycle
// Changelog:10 Feb.2022 (F.Loddo): HitDelay = 1 Cycle - deltaHitdelay  (typically 25-5 ns

// **NOTE: dedicated time-scale and time-precision directives inside the module implementation !
package afe_params_functions;
    // Use exact CLOCK_PERIOD as a reference for hit injection and for tot_busy flag generation (has to match with common defines)
    parameter integer CLOCK_PERIOD_1ps = 25024;
    
    // in case some random jitter due to transient-noise is added on the DISC output pulse using $random()
    integer seed = 15 ;
    parameter integer rmsJitterLE = 100 ;    // [ps]
    parameter integer rmsJitterTE = 1000 ;   // [ps]    **NOTE: the RMS jitter on the trailing-edge is much larger than the leading-edge one !
    ////////////////////////////
    // front-end parameters   //
    ////////////////////////////

    //
    // sensor parameters
    //
    parameter real Cpixel = 50e-15 ;                 // assume 50 fF total input capacitance
    parameter real Ileak = 10e-9 ;                   // assume 10 nA leakage current (not used) 

    parameter real time2charge = 10.000 ;            // assume 1ps = 10 electrons
    parameter real Qmin = 600.0*1.6e-19 ;            // assume 600e minimum detectable signal as from specs
    parameter real deltaHitDelay =5000;              // This is subtraxcted from the CLOCK_PERIOD_1ps  to give a delay of 20 ns from the input 

    //
    // charge-injection circuit parameters
    //
    parameter real calHi = 500.0e-3  ;               // sample CAL_HI value
    parameter real calMi =  50.0e-3  ;               // nominal 50 mV CAL_LO value
    
    //
    // Charge Sensitive Amplifier (CSA) parameters
    //
    parameter real Cinj =  8.0e-15 ;                 // assume 8 fF calibration circuit injection capacitance
    parameter real Cfeed = 5e-15 ;                   // assume 5 fF feedback capacitance 
    parameter real Ifeed = 7e-9 ;                    // assume 7 nA constant-current feedback ( cover all 15 TOT codes in std sim )
    //parameter real Ifeed = 19e-9 ;                 // assume 19 nA constant-current feedback (~3ke/TOT ) to contain dead-time losses

    parameter real Gm = 50e-6 ;                      // assume 50 uS effective input transconductance (mainly from input transistor)
    parameter real Cin = 10e-15 ;                    // assume 10 fF total gate-source input capacitance

    parameter real Aol = 1e3 ;                       // assume open-loop gain >= 1e3 to ensure approx. 100% charge-collection efficiency
    parameter real Rout = 10e6 ;                     // assume 10 Mohm small-signal output resistance
    parameter real Cout = 10e-15 ;                   // assume 10 fF output capacitance (before output source follower), resulting into approx. 1.6 MHz open-loop BW 

    parameter real csaRiseTime = 2.2*((Cpixel + Cin + Cout) + ((Cpixel + Cin)*Cout/Cfeed)/Gm)*1e12 ; // CSA rise-time in ps (independent from input charge)

    //
    // discriminator (DISC) parameters
    //

    // **NOTE: the discriminator is modeled as an ideal voltage comparator with
    //         a single-pole transfer function H(s) = 1/(1+s/omega) with a pole
    //         omega = 1/tau = RC and BW = 1/(2pi RC), leading to a logarithmic
    //         propagation delay (time-walk) as from literature

    parameter real BW = 5e6 ;                        // assume 5 MHz BW for the discriminator (LIN front-end has 3 MHz)
    parameter real tau = 1/(6.28*BW) ;               // time-constant associated to the LP filter
    
    // compute the **effective** input charge (some charge is lost on detector capacitance if Aol < inf.)
    function real GetIntegratedCharge ;
        
       input real charge ;
       
       begin
          GetIntegratedCharge = ((1+Aol)*Cfeed/(Cpixel + (1+Aol)*Cfeed))*charge ;
       end

    endfunction : GetIntegratedCharge

    //_____________________________________________________________________________________


    // compute the ToT from (optionally the integrated) charge [ps]
    function real GetTotFromCharge ;

       input real charge ;

       begin
          `ifndef TOT_MULTIPLE_25ns
            GetTotFromCharge = charge/Ifeed*1e12 ;   // **NOTE: this has to be replaced by a FE-specific look-up table or some polynomial FIT on simulated data !
          `else // for GL simulations, where edges can cause violations
            if ((charge/Ifeed*1e12)>CLOCK_PERIOD_1ps)
               GetTotFromCharge = $rtoi(charge/Ifeed*1e12/CLOCK_PERIOD_1ps) ;
            else
               //GL only (TOT_MULTIPLE_25ns): avoid a short pulse being converted in a #0 pulse in waveform AND ref model having =0 hits.
               GetTotFromCharge = 1; 
          `endif
       end

    endfunction : GetTotFromCharge

    //_____________________________________________________________________________________


    // compute the time-walk [ps]
    function real GetTimeWalkFromCharge ;

       input real charge ;


       begin

          real alpha ;            // **WARN: this would be a ratio between voltages (Vin/Vmin), but we assume linearity between charge and amplitude
          alpha = charge/Qmin ;

          if( 2*alpha/(2*alpha-1) > 0.0)
             GetTimeWalkFromCharge = tau * $ln(2*alpha/(2*alpha-1)) * 1e12 ;   // **NOTE: this has to be replaced by a FE-specific look-up table or some polynomial FIT on simulated data !
          else
             GetTimeWalkFromCharge = 0.000 ;
       end

    endfunction : GetTimeWalkFromCharge

    //_____________________________________________________________________________________

endpackage: afe_params_functions

import afe_params_functions::*;

module RD53B_AFE_DIFF (
    
   // power/ground
`ifdef PGPINS
   inout wire VDDA,      // **WARN: P/G pins are **NOT** connected in RTL, but this information is contained in OA views and the Liberty description instead
   inout wire VDDA_REF,
   inout wire GNDA,
   inout wire VSUB,
   inout wire VDDD,
   inout wire GNDD,
`endif

   // bias lines
   inout wire VBP_PREAMP,
   inout wire VBN_COMP,
   inout wire VBN_PRECOMP,
   inout wire VTH1,
   inout wire VTH2,
   inout wire VBN_LCC,
   inout wire VBP_VFF,
   inout wire VCTRL_CF0,
   inout wire VCTRL_LCC,

   // configuration
   input wire [3:0] DTH1,
   input wire [3:0] DTH2,

   // calibration circuit DC levels and charge-injection signals
   inout wire VCAL_HI,
   inout wire VCAL_MI,
   input wire S0,
   input wire S1,

   // input stimulus from the simulation environment, but also a physical
   // pin connected to the bump pad in the full-custom OA layout
   input wire BUMP,

   // DISC output
   output wire DISC_OUT

   ) ;


   // **WARN: non-synthesizable behavioural code

   // synopsys translate_off


   ////////////////////////////////////////////////////////////////
   //   local module timescale/timeprecision - **DO NOT EDIT**   //
   ////////////////////////////////////////////////////////////////

   timeunit      1ps ;            // **WARN: 1ps time-unit is required to get real charge values from time intervals !
   timeprecision 1ps ;

   //
   // charge-ijection circuit parameters
   //

   // Flags for hit loss prediction
   logic tot_busy = 1'b0; // the FE is still driving the previous TOT and if receving a new hit they will overlap (prevent overlapping)

   ///////////////////////////////////////////
   //   charge-injection through BUMP pad   //
   ///////////////////////////////////////////

   // internal variables for computations (get real charge from pulse width)

   //realtime t1, t2 ;                              // **WARN: 'realtime' is 64-bit DOUBLE-precision floating point to be used with $realtime system task
   time t1, t2 ;                                    // **WARN: 'time' is 64-bit UNSIGNED integer to be used with $time system task (in ps since timescale is ps)

   logic hitBump = 1'b0 ;

   // detect when the rising-edge of BUMP pulse occurs
   always @(posedge BUMP) begin
      if( $time != 0)
         t1 = $time ;                               // **WARN: use blocking assignments ! This is just "software language"         
    end


   // detect when the falling-edge of BUMP pulse occurs and compute ToT and total charge-to-output delay (CSA rise-time + DISC time-walk + jitter)
   // **WARN: with this approach (2 clock cycles delay, it is prevented to send hits at 1 clock cycle distance in some cases)
   always @(negedge BUMP) begin : injBump

      real Qin, Qfeed, ToT, timeWalk, hitDelay, hitDelayNextClk ;    // local variables

      //integer seed = 10 ;
      integer jitterLE, jitterTE ;
      
      if (!tot_busy) begin // Veto hit generation if tot_busy (or hits will pileup and will not be able to clasify the reason)
         if( $time != 0 && t1 > 0) begin
            t2 = $time ;                               // **WARN: use blocking assignments ! This is just "software language"
            jitterLE = 0; //$dist_normal(seed, 0, rmsJitterLE) ;
            jitterTE = 0; //$dist_normal(seed, 0, rmsJitterTE) ;

            // **total** input charge
            Qin = (t2-t1)*time2charge*1.6e-19 ;

            // **effective** input charge
            Qfeed = Qin ;//GetIntegratedCharge(Qin) ;

            // DISC time-walk
            timeWalk = 0; //GetTimeWalkFromCharge(Qfeed) ;

            // Time-over-Threshold
            ToT = GetTotFromCharge(Qfeed) ;

            // combine CSA rise-time (charge-independent) and DISC time-walk
            
	    `ifdef MAX_CORNER
	        hitDelay =  CLOCK_PERIOD_1ps - (t2-t1) + 5000  ; // delay to align to the pixel array clock (hits are genereted aligned to periphery) or will cause violations in cnt_clk_latch, ff0, etc.
	    `else
//	    	hitDelay =  CLOCK_PERIOD_1ps - (t2-t1) - csaRiseTime*0.5 + timeWalk ; // Assume that system clock is aligned to half of csaRiseTime		
	    	hitDelay =  CLOCK_PERIOD_1ps - (t2-t1) - deltaHitDelay + timeWalk ; // 10 Feb 2022 - F.L. Removed csaRiseTime. Now hitDelay is posedge Bump + 1 clock period -deltaHitDelay 
	    `endif
	    
	    fork begin
               // generate the DISC output pulse
               #(hitDelay + jitterLE) hitBump = 1'b1 ;
               `ifndef TOT_MULTIPLE_25ns
                  #(ToT + jitterTE) hitBump = 1'b0 ;
               `else
                  #(ToT*CLOCK_PERIOD_1ps + jitterTE) hitBump = 1'b0 ;
               `endif
            end join_none

            // **DEBUG
            //$display("t1 = %d [ps]", t1 ) ;
            //$display("t2 = %d [ps]", t2 ) ;
            //$display("input charge = %10.4g [C] ; integrated charge = %10.4g [C] ; ToT = %8.f [ps] ; charge-to-hit delay = %6.f [ps]", Qin, Qfeed, ToT, hitDelay) ;
     
         end   // $time != 0
     end // if (!tot_busy)
   end   // always @(negedge BUMP)
   
   // Separate always to generate in parallel the tot_busy flag synchronous to clock
   always @(negedge BUMP) begin : totBusyFlag

      real Qin, Qfeed, ToT, timeWalk, hitDelay, hitDelayNextClk ;    // local variables

      //integer seed = 10 ;
      integer jitterLE, jitterTE ;
      
      if( $time != 0 && t1 > 0) begin
         t2 = $time ;                               // **WARN: use blocking assignments ! This is just "software language"

         jitterLE = 0; //$dist_normal(seed, 0, rmsJitterLE) ;
         jitterTE = 0; //$dist_normal(seed, 0, rmsJitterTE) ;
         // **total** input charge
         Qin = (t2-t1)*time2charge*1.6e-19 ;
         // **effective** input charge
         Qfeed = Qin ;//GetIntegratedCharge(Qin) ;
         // Time-over-Threshold
         `ifndef TOT_MULTIPLE_25ns
         ToT = $rtoi(GetTotFromCharge(Qfeed)/CLOCK_PERIOD_1ps) ; // Ps to integer number of clock cycles
         `else
         ToT = GetTotFromCharge(Qfeed) ; // Ps to integer number of clock cycles
         `endif
         // combine CSA rise-time (charge-independent) and DISC time-walk
         hitDelayNextClk = CLOCK_PERIOD_1ps - (t2-t1) ;
         // generate the tot_busy flag and be sure that it is synchronous with the clock (no custom delays, timewalk, etc.)
         #(hitDelayNextClk)               tot_busy = 1'b1 ;
         #((ToT+1)*CLOCK_PERIOD_1ps)      tot_busy = 1'b0 ; // Bring it down slightly later than clock posedge or mismatch

      end   // $time != 0
  end: totBusyFlag   // always @(negedge BUMP)

   //////////////////////////////////////////////////////
   //   charge-injection through calibration circuit   //
   //////////////////////////////////////////////////////

   logic hitInjS0 = 1'b0 ;
   logic hitInjS1 = 1'b0 ;

   // first injection
   always @(posedge S0) begin : injS0

      real Qin, Qfeed, ToT, timeWalk, hitDelay ;    // local variables

      //integer seed = 10 ;
      integer jitterLE, jitterTE ;

         jitterLE = 0; // $dist_normal(seed, 0, rmsJitterLE) ;  3 Feb. 2022 F.L.
         jitterTE = 0; // $dist_normal(seed, 0, rmsJitterTE) ; 3 Feb. 2022 F.L.

         // **total** input charge
         Qin = (calHi - calMi)*Cinj ;

         // **effective** input charge
         Qfeed = Qin; // GetIntegratedCharge(Qin) ; 3 Feb. 2022 F.L.

         // DISC time-walk
         timeWalk = 0; // GetTimeWalkFromCharge(Qfeed) ; 3 Feb. 2022 F.L.

         // Time-over-Threshold
         ToT = GetTotFromCharge(Qfeed) ;
         
         // combine CSA rise-time (charge-independent) and DISC time-walk
//         hitDelay = CLOCK_PERIOD_1ps + csaRiseTime + timeWalk ;     // **WARN: in order to re-scale the computing time, align t=0 to the next rising edge of the clock !
	       hitDelay =  CLOCK_PERIOD_1ps - deltaHitDelay + timeWalk ; // 10 Feb 2022 - F.L. Removed csaRiseTime. Now hitDelay is  1 clock period - deltaHitDelay from posedge S0/S1 

         // generate the DISC output pulse
         #(hitDelay + jitterLE) hitInjS0 = 1'b1 ;
         `ifndef TOT_MULTIPLE_25ns
            #(ToT + jitterTE)      hitInjS0 = 1'b0 ;
         `else
             #(ToT*CLOCK_PERIOD_1ps + jitterTE)      hitInjS0 = 1'b0 ;        
         `endif

         // **DEBUG
         //$display("input charge = %10.4g [C] ; integrated charge = %10.4g [C] ; ToT = %8.f [ps] ; charge-to-hit delay = %6.f [ps]", Qin, Qfeed, ToT, hitDelay) ;

   end   // always @(posedge S0)


   // second injection
   always @(posedge S1) begin : injS1

      real Qin, Qfeed, ToT, timeWalk, hitDelay ;    // local variables

      //integer seed = 10 ;
      integer jitterLE, jitterTE ;

         jitterLE = 0; // $dist_normal(seed, 0, rmsJitterLE) ;  3 Feb. 2022 F.L.
         jitterTE = 0; // $dist_normal(seed, 0, rmsJitterTE) ; 3 Feb. 2022 F.L.

         // **total** input charge
         Qin = calMi*Cinj ;

         // **effective** input charge
         Qfeed =  Qin; // GetIntegratedCharge(Qin) ; 3 Feb. 2022 F.L.

         // DISC time-walk
         timeWalk = 0; // GetTimeWalkFromCharge(Qfeed) ; 3 Feb. 2022 F.L.

         // Time-over-Threshold
         ToT = GetTotFromCharge(Qfeed) ;

         // combine CSA rise-time (charge-independent) and DISC time-walk
//         hitDelay = CLOCK_PERIOD_1ps + csaRiseTime + timeWalk ;     // **WARN: in order to re-scale the computing time, align t=0 to the next rising edge of the clock !
	       hitDelay =  CLOCK_PERIOD_1ps - deltaHitDelay + timeWalk ; // 10 Feb 2022 - F.L. Removed csaRiseTime. Now hitDelay is  1 clock period - deltaHitDelay from posedge S0/S1 

         // generate the DISC output pulse
         #(hitDelay + jitterLE) hitInjS1 = 1'b1 ;
         `ifndef TOT_MULTIPLE_25ns
             #(ToT + jitterTE)      hitInjS1 = 1'b0 ;
         `else
             #(ToT*CLOCK_PERIOD_1ps + jitterTE)      hitInjS1 = 1'b0 ;        
         `endif
         // **DEBUG
         //$display("input charge = %10.4g [C] ; integrated charge = %10.4g [C] ; ToT = %8.f [ps] ; charge-to-hit delay = %6.f [ps]", Qin, Qfeed, ToT, hitDelay) ;

   end   // always @(posedge S0)


   //////////////////////////
   //   DISC output pulse   //
   ///////////////////////////

   // switch between external hit and test hit

   logic hitDisc ;

   always_comb begin 

      // simple OR model of external hit and two injection signals (S0 and S1) with different amplitudes
      if( hitBump || hitInjS0 || hitInjS1) 
         hitDisc = hitBump | hitInjS0 | hitInjS1 ;
      else
         hitDisc = 1'b0 ;
   end   // always

   assign DISC_OUT = hitDisc ;

   // synopsys translate_on

endmodule : RD53B_AFE_DIFF

`endif   // RD53B_AFE_DIFF_REALMODEL__SV	    	hitDelay =  CLOCK_PERIOD_1ps - (t2-t1) + timeWalk ; // 4 Feb 2022 - F.L. Removed csaRiseTime. Now hitDelay is posedge Bump + 1 clock period